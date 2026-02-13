# v0.9.5 (Multi-Delete Support)

import os
import sys
import json
import asyncio
import html
from datetime import datetime, timedelta
from telethon import TelegramClient, events, utils
from telethon.tl.types import User, Channel, Chat, UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth, DocumentAttributeAudio, DocumentAttributeVideo
from prompt_toolkit import PromptSession, print_formatted_text, HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

# --- Configuration (Absolute Paths) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(SCRIPT_DIR, 'simplegram_session')
API_CONFIG_FILE = os.path.join(SCRIPT_DIR, 'api_config.json') 
SETTINGS_FILE = os.path.join(SCRIPT_DIR, 'settings.json')

# --- Default Settings ---
DEFAULT_SETTINGS = {
    "defaultHistory": 0,      # Default is 0 (No history auto-load)
    "autoClearMsgLog": False  # Default is False (Input line remains visible)
}

# --- UI Styles ---
style = Style.from_dict({
    'user': '#888888',       # Gray 
    'sent': "#11ba11",       # Dark Green
    'error': '#ff0000',      # Red
    'system': "#d5d518",     # Dark Yellow
    'plain': "#dedede",      # Light Gray
    'info': "#0bcece",       # Blue
    'date': 'bg:#333333 #ffffff', # White on dark gray background
    'unread': '#ff00ff',     # Magenta for unread counts
    'type': '#5f5f5f italic', # Dark gray italic for chat types
    'reply': '#ffaf00 italic', # Orange italic for reply context
    'index': '#888888 bold', # Grey bold for message indices
})

# --- Helper Function for API Keys ---
def get_api_credentials():
    if not os.path.exists(API_CONFIG_FILE):
        print_formatted_text(HTML("<system>⚠️ api_config.json not found.</system>"), style=style)
        print_formatted_text(HTML("<info>ℹ️  To get your Telegram API keys:</info>"), style=style)
        print_formatted_text(HTML("<info>   1. Log in to https://my.telegram.org</info>"), style=style)
        print_formatted_text(HTML("<info>   2. Go to 'API development tools'</info>"), style=style)
        print_formatted_text(HTML("<info>   3. Create a new application (any name works)</info>"), style=style)
        print("")
        
        print("Please enter your API_ID: ", end="", flush=True)
        api_id = sys.stdin.readline().strip()
        print("Please enter your API_HASH: ", end="", flush=True)
        api_hash = sys.stdin.readline().strip()
        
        if not api_id or not api_hash:
             print_formatted_text(HTML("<error>❌ API credentials cannot be empty. Exiting.</error>"), style=style)
             sys.exit(1)

        data = {"api_id": api_id, "api_hash": api_hash}
        try:
            with open(API_CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            print_formatted_text(HTML(f"<system>✅ Saved API credentials to {API_CONFIG_FILE}</system>"), style=style)
            return api_id, api_hash
        except Exception as e:
            print_formatted_text(HTML(f"<error>❌ Failed to write config file: {e}</error>"), style=style)
            sys.exit(1)
    else:
        try:
            with open(API_CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data['api_id'], data['api_hash']
        except Exception as e:
            print_formatted_text(HTML(f"<error>❌ Error reading api_config.json: {e}</error>"), style=style)
            print_formatted_text(HTML(f"<error>Please check the file or delete it to reset.</error>"), style=style)
            sys.exit(1)

# --- Settings Functions ---
def load_settings():
    """Loads settings.json, creating it with defaults if missing, and appending new defaults retroactively."""
    settings = DEFAULT_SETTINGS.copy()
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved_settings = json.load(f)
                # Update defaults with saved values (preserves new defaults if not in file)
                settings.update(saved_settings)
        except Exception as e:
            print_formatted_text(HTML(f"<error>❌ Error reading settings.json: {e}</error>"), style=style)
    
    # Save back to ensure file exists and has latest keys
    save_settings(settings)
    return settings

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print_formatted_text(HTML(f"<error>❌ Failed to save settings: {e}</error>"), style=style)

# --- Helper Functions ---
def get_display_name(entity):
    """Safely get a display name regardless of entity type"""
    if hasattr(entity, 'first_name') and entity.first_name:
        last = getattr(entity, 'last_name', '') or ''
        return f"{entity.first_name} {last}".strip()
    elif hasattr(entity, 'title'):
        return entity.title
    return "Unknown"

def get_entity_type_label(entity):
    """Returns a short label for the entity type"""
    if isinstance(entity, User):
        return "User"
    elif isinstance(entity, Chat):
        return "Group"
    elif isinstance(entity, Channel):
        if entity.broadcast:
            return "Channel"
        return "Group"
    return "Unknown"

def get_user_status(entity):
    """Parse UserStatus object into readable string"""
    if not isinstance(entity, User):
        return None 
    
    if not hasattr(entity, 'status') or not entity.status:
        return "Offline"
    
    s = entity.status
    if isinstance(s, UserStatusOnline):
        return "🟢 Online"
    elif isinstance(s, UserStatusOffline):
        if s.was_online:
            return f"Last seen: {s.was_online.astimezone().strftime('%Y-%m-%d %H:%M')}"
        return "Offline"
    elif isinstance(s, UserStatusRecently):
        return "Last seen recently"
    elif isinstance(s, UserStatusLastWeek):
        return "Last seen last week"
    elif isinstance(s, UserStatusLastMonth):
        return "Last seen last month"
    
    return "Offline"

def format_message_content(message):
    """Helper to format message content (Text, Voice, Video Note, File)"""
    content = ""
    
    if message.voice:
        duration = message.file.duration if message.file and message.file.duration else "?"
        content = f"[Voice Message ({duration}s)]"
    elif message.video_note:
        duration = message.file.duration if message.file and message.file.duration else "?"
        content = f"[Video Note ({duration}s)]"
    elif message.file:
        file_name = "unknown file"
        if hasattr(message.file, 'name') and message.file.name:
            file_name = message.file.name
        elif message.document and hasattr(message.document, 'attributes'):
            for attr in message.document.attributes:
                if hasattr(attr, 'file_name') and attr.file_name:
                    file_name = attr.file_name
        content = f'[File: "{file_name}"]'
    elif message.text:
        content = html.escape(str(message.text))
    elif message.action:
        content = f"[{type(message.action).__name__}]"
    else:
        content = "[Media/Sticker]"
        
    return content

# --- Helper Class to Track State ---
class ChatSession:
    def __init__(self, entity):
        self.entity = entity
        self.name = get_display_name(entity)
        self.last_message_date = None
        self.reply_to_msg_id = None  
        self.reply_snippet = None
        self.message_index_map = {} # Maps visual index [1] to message ID
        self.next_index = 1         # Counter for next incoming message

async def main():
    api_id, api_hash = get_api_credentials()
    client = TelegramClient(SESSION_FILE, api_id, api_hash)
    
    # Load Settings
    user_settings = load_settings()
    
    print_formatted_text(HTML("<system>🚀 Connecting to Telegram...</system>"), style=style)
    await client.start()

    # --- STATE ---
    current_chat = None 
    chat_list_cache = [] # Stores entities for the /chats command so /c [n] works

    print_formatted_text(HTML("<system>✅ Connected! Type /help to see commands, or /chats to browse conversations.</system>"), style=style)

    # --- CHAT PHASE ---
    session = PromptSession()
    
    def print_date_separator(message_date):
        if not current_chat: return
        msg_date_obj = message_date.date()
        if current_chat.last_message_date != msg_date_obj:
            date_str = msg_date_obj.strftime("%A, %B %d, %Y")
            print_formatted_text(HTML(f"<date>  📅 {date_str}  </date>"), style=style)
            current_chat.last_message_date = msg_date_obj

    # Helper function to render history (used by /history and auto-load)
    async def fetch_and_render_history(limit_count):
        if not current_chat: return
        # Safety check: if 0 or negative, do nothing
        if limit_count <= 0: return

        print_formatted_text(HTML(f"<system>⏳ Fetching last {limit_count} messages...</system>"), style=style)
        try:
            history_msgs = await client.get_messages(current_chat.entity, limit=limit_count)
            print_formatted_text(HTML(f"<system>--- History ({len(history_msgs)}) ---</system>"), style=style)
            
            history_last_date = None
            
            # Reset mapping and counter for this chat view
            current_chat.message_index_map = {}
            current_chat.next_index = 1
            
            # Capture chronological list to assign indices 1..N
            chronological_msgs = list(reversed(history_msgs))

            for message in chronological_msgs:
                msg_date = message.date.astimezone()
                if history_last_date != msg_date.date():
                    date_str = msg_date.strftime("%A, %B %d, %Y")
                    print_formatted_text(HTML(f"<date>  📅 {date_str}  </date>"), style=style)
                    history_last_date = msg_date.date()

                time_str = msg_date.strftime('%H:%M')
                
                # Assign Index
                idx = current_chat.next_index
                current_chat.message_index_map[idx] = message
                current_chat.next_index += 1
                
                idx_str = f"[{idx}]"

                if message.out:
                    sender_label = f"<index>{idx_str}</index> [{time_str}] [You]"
                else:
                    sender_name = current_chat.name
                    if message.sender:
                            sender_name = get_display_name(message.sender)
                    sender_label = f"<index>{idx_str}</index> [{time_str}] [{html.escape(sender_name)}]"

                # Use helper function for content
                content = format_message_content(message)
                
                # Reply indicator in history
                reply_indicator = " (reply)" if message.is_reply else ""

                if message.out:
                    print_formatted_text(HTML(f"<sent>{sender_label}{reply_indicator}: {content}</sent>"), style=style)
                else:
                    print_formatted_text(HTML(f"<plain>{sender_label}{reply_indicator}: {content}</plain>"), style=style)
                    
            print_formatted_text(HTML(f"<system>--- End of History ---</system>"), style=style)
            if history_last_date:
                current_chat.last_message_date = history_last_date
        except Exception as e:
                print_formatted_text(HTML(f"<error>❌ Error fetching history: {e}</error>"), style=style)


    @client.on(events.NewMessage())
    async def handler(event):
        if not current_chat or event.chat_id != current_chat.entity.id:
            return

        with patch_stdout():
            print_date_separator(event.date.astimezone())
            raw_text = event.raw_text
            time_str = event.date.astimezone().strftime('%H:%M')
            
            # Assign Index to new live message
            idx = current_chat.next_index
            current_chat.message_index_map[idx] = event.message
            current_chat.next_index += 1
            idx_str = f"[{idx}]"

            if event.out:
                label = f"<index>{idx_str}</index> [{time_str}] [You]"
            else:
                sender_name = current_chat.name
                if event.sender:
                     sender_name = get_display_name(event.sender)
                label = f"<index>{idx_str}</index> [{time_str}] [{html.escape(sender_name)}]"
            
            # Use new helper function
            safe_raw = format_message_content(event)

            # Indication if it's a reply
            reply_indicator = ""
            if event.is_reply:
                reply_indicator = " (reply)"

            if event.out:
                print_formatted_text(HTML(f"<sent>{label}{reply_indicator}: {safe_raw}</sent>"), style=style)
            else:
                print_formatted_text(HTML(f"<plain>{label}{reply_indicator}: {safe_raw}</plain>"), style=style)

    while True:
        try:
            with patch_stdout():
                # Dynamic prompt logic
                prompt_text = "<b>You: </b>"
                
                if current_chat:
                    safe_prompt_name = html.escape(current_chat.name)
                    base_prompt = f"<b>You (to {safe_prompt_name}): </b>"
                    
                    # If Reply Mode is Active
                    if current_chat.reply_to_msg_id:
                        snippet = html.escape(current_chat.reply_snippet)
                        prompt_text = f"<reply>...{snippet} >> </reply>{base_prompt}"
                    else:
                        prompt_text = base_prompt
                
                msg = await session.prompt_async(HTML(prompt_text))

            # --- OPTIONAL CLEAR INPUT LINE LOGIC ---
            if user_settings.get("autoClearMsgLog", False):
                sys.stdout.write("\033[1A\033[2K")
                sys.stdout.flush()
            # ----------------------------------------

            cmd = msg.strip().split()
            msg_clean = msg.strip()
            
            if not msg_clean: continue

            if msg_clean in ['/exit', '--exit']:
                break
            
            elif msg_clean in ['/help', '/h']:
                help_text = """
<system>Available Commands:

--- Navigation ---
/chats [type] [n]   : List recent conversations. 
/c [n]              : Jump to chat number [n] from the last /chats list.
/contacts [n]       : List [n] most recent contacts (Users only).
/contacts abc [n]   : List contacts ALPHABETICALLY.

--- Chatting ---
/r [name]           : Chat with a user/group (e.g., "/r @alice").
/r off              : Close current chat. Aliases: //, /out.
/reply [n]          : Reply to message number [n].
/reply              : Reply to THEIR last message.
/delete [n] [n]...  : Delete message numbers for everyone (e.g., /del 5 6 7).
/history [n], /h [n]: Show last [n] messages.

--- Settings ---
/settings           : Change or view settings.
/set [key] [val]    : Alias for settings.
/set help           : See the list of available settings. 

--- General ---
/help               : Show this list.
/exit               : Quit the application.</system>
"""
                print_formatted_text(HTML(help_text), style=style)

            # --- SETTINGS COMMAND ---
            elif msg_clean.startswith('/settings') or msg_clean.startswith('/set '):
                args = cmd[1:]
                
                if not args:
                    # Show current settings
                    print_formatted_text(HTML("<info>--- Current Settings ---</info>"), style=style)
                    for k, v in user_settings.items():
                        print_formatted_text(HTML(f"<plain>{k}: {v}</plain>"), style=style)
                    print_formatted_text(HTML("<system>Usage: /settings [name] [value]</system>"), style=style)
                
                elif args[0].lower() == 'help':
                    # Show help for settings
                    print_formatted_text(HTML("<info>--- Settings Help ---</info>"), style=style)
                    print_formatted_text(HTML("<plain><b>defaultHistory</b> [0-100]: Number of messages to load automatically when opening a chat (0 to disable).</plain>"), style=style)
                    print_formatted_text(HTML("<plain><b>autoClearMsgLog</b> [true/false]: Clear your input line from terminal after sending (cleaner UI).</plain>"), style=style)
                
                elif len(args) >= 2:
                    key = args[0]
                    value = args[1]
                    
                    if key == "defaultHistory":
                        if value.isdigit() and 0 <= int(value) <= 100:
                            user_settings[key] = int(value)
                            save_settings(user_settings)
                            print_formatted_text(HTML(f"<system>✅ Set {key} to {value}.</system>"), style=style)
                        else:
                            print_formatted_text(HTML(f"<error>❌ Value for defaultHistory must be a number between 0 and 100.</error>"), style=style)
                    else:
                         try:
                             if value.isdigit(): value = int(value)
                             elif value.lower() == 'true': value = True
                             elif value.lower() == 'false': value = False
                             
                             user_settings[key] = value
                             save_settings(user_settings)
                             print_formatted_text(HTML(f"<system>✅ Set {key} to {value}.</system>"), style=style)
                         except Exception as e:
                             print_formatted_text(HTML(f"<error>❌ Could not save setting: {e}</error>"), style=style)
                else:
                    print_formatted_text(HTML("<error>❌ Usage: /settings [name] [value] or /settings help</error>"), style=style)

            # --- EXIT CHAT COMMANDS ---
            elif msg_clean in ['/r off', '//', '/out']:
                if current_chat:
                    print_formatted_text(HTML(f"<system>🔌 Closed chat with {html.escape(current_chat.name)}.</system>"), style=style)
                    current_chat = None
                else:
                    print_formatted_text(HTML("<system>You are not in a chat.</system>"), style=style)

            # --- STATUS COMMAND ---
            elif msg_clean in ['/status', '/s']:
                if current_chat:
                    try:
                        full_entity = await client.get_entity(current_chat.entity.id)
                        status_text = get_user_status(full_entity)
                        if status_text:
                            print_formatted_text(HTML(f"<info>ℹ️  Status: {status_text}</info>"), style=style)
                        else:
                            print_formatted_text(HTML(f"<info>ℹ️  Status: N/A</info>"), style=style)
                    except Exception as e:
                        print_formatted_text(HTML(f"<error>❌ Could not fetch status: {e}</error>"), style=style)
                else:
                    print_formatted_text(HTML("<error>❌ No active chat.</error>"), style=style)

            # --- REPLY COMMAND ---
            elif msg_clean.startswith('/re') or msg_clean.startswith('/reply'):
                if not current_chat:
                    print_formatted_text(HTML("<error>❌ No active chat.</error>"), style=style)
                elif "cancel" in msg_clean:
                    current_chat.reply_to_msg_id = None
                    current_chat.reply_snippet = None
                    print_formatted_text(HTML("<system>Reply cancelled.</system>"), style=style)
                elif current_chat.reply_to_msg_id is not None and len(cmd) == 1:
                     current_chat.reply_to_msg_id = None
                     current_chat.reply_snippet = None
                     print_formatted_text(HTML("<system>Reply cancelled.</system>"), style=style)
                else:
                    target_msg = None
                    
                    if len(cmd) > 1 and cmd[1].isdigit():
                        idx = int(cmd[1])
                        if idx in current_chat.message_index_map:
                            target_msg = current_chat.message_index_map[idx]
                        else:
                            print_formatted_text(HTML(f"<error>❌ Message [{idx}] not found in current view.</error>"), style=style)
                            continue 
                    else:
                        print_formatted_text(HTML("<system>🔄 Finding last message from recipient...</system>"), style=style)
                        async for message in client.iter_messages(current_chat.entity, limit=50):
                            if not message.out:
                                target_msg = message
                                break
                    
                    if target_msg:
                        current_chat.reply_to_msg_id = target_msg.id
                        text = format_message_content(target_msg)
                        snippet = text[-15:] if len(text) > 15 else text
                        current_chat.reply_snippet = snippet
                    else:
                        if len(cmd) == 1:
                            print_formatted_text(HTML("<error>❌ No messages from recipient found to reply to.</error>"), style=style)

            # --- DELETE COMMAND (UPDATED) ---
            elif cmd[0] in ['/delete', '/del', '/rm']:
                if not current_chat:
                    print_formatted_text(HTML("<error>❌ No active chat.</error>"), style=style)
                elif len(cmd) < 2:
                    print_formatted_text(HTML("<error>❌ Usage: /delete [n1] [n2] ... (e.g., /del 5 6 7)</error>"), style=style)
                else:
                    msgs_to_delete = []
                    valid_indices = []
                    
                    # 1. Parse and Collect valid messages
                    for arg in cmd[1:]:
                        if arg.isdigit():
                            idx = int(arg)
                            if idx in current_chat.message_index_map:
                                msgs_to_delete.append(current_chat.message_index_map[idx])
                                valid_indices.append(idx)
                            else:
                                print_formatted_text(HTML(f"<error>⚠️ Index [{idx}] not found (skipped).</error>"), style=style)
                        else:
                            print_formatted_text(HTML(f"<error>⚠️ '{arg}' is not a number (skipped).</error>"), style=style)
                    
                    if not msgs_to_delete:
                        print_formatted_text(HTML("<error>❌ No valid messages selected to delete.</error>"), style=style)
                    else:
                        # 2. Check for ownership (Safety Check)
                        contains_others_messages = any(not m.out for m in msgs_to_delete)
                        
                        # 3. Construct Warning
                        indices_str = ", ".join([f"[{i}]" for i in valid_indices])
                        
                        if contains_others_messages:
                            print_formatted_text(HTML(f"<error>⚠️ WARNING: One or more selected messages were sent by the recipient!</error>"), style=style)
                        
                        warning_msg = f"<system>⚠️ Are you sure you want to delete messages {indices_str} for everyone?</system>"
                        print_formatted_text(HTML(warning_msg), style=style)
                        
                        # 4. Confirmation Prompt
                        with patch_stdout():
                            confirm = await session.prompt_async(HTML("<system>Type 'y' to confirm: </system>"))
                        
                        if confirm.lower() == 'y':
                            try:
                                msg_ids = [m.id for m in msgs_to_delete]
                                await client.delete_messages(current_chat.entity, msg_ids, revoke=True)
                                print_formatted_text(HTML(f"<system>🗑️ Deleted {len(msg_ids)} messages for everyone.</system>"), style=style)
                            except Exception as e:
                                print_formatted_text(HTML(f"<error>❌ Failed to delete: {e}</error>"), style=style)
                        else:
                            print_formatted_text(HTML("<system>Deletion cancelled.</system>"), style=style)

            # --- CONTACTS COMMAND ---
            elif msg_clean.startswith('/contacts'):
                sort_alpha = False
                target_count = 10 
                args = cmd[1:]
                if 'abc' in args:
                    sort_alpha = True
                    target_count = 25 
                    args.remove('abc')
                if args:
                    if args[0] == 'all':
                        target_count = 999999
                    elif args[0].isdigit():
                        target_count = int(args[0])

                label = 'Alphabetical' if sort_alpha else 'Recent'
                print_formatted_text(HTML(f"<system>⏳ Fetching {target_count if target_count < 9999 else 'all'} contacts ({label})...</system>"), style=style)
                try:
                    user_dialogs = []
                    count_found = 0
                    async for dialog in client.iter_dialogs():
                        if dialog.is_user and not dialog.entity.bot:
                            user_dialogs.append(dialog.entity)
                            count_found += 1
                            if not sort_alpha and count_found >= target_count:
                                break
                    if sort_alpha:
                        user_dialogs.sort(key=lambda x: get_display_name(x).lower())
                        if target_count < len(user_dialogs):
                            user_dialogs = user_dialogs[:target_count]

                    print_formatted_text(HTML(f"<info>--- Contacts List ({len(user_dialogs)}) ---</info>"), style=style)
                    for entity in user_dialogs:
                        display_name = get_display_name(entity)
                        username = getattr(entity, 'username', None)
                        phone = getattr(entity, 'phone', None)
                        contact_info = []
                        if username: contact_info.append(f"@{username}")
                        if phone: contact_info.append(f"+{phone}")
                        info_str = ", ".join(contact_info)
                        print_formatted_text(HTML(f"<plain>• <b>{html.escape(display_name)}</b> ({html.escape(info_str)})</plain>"), style=style)
                    print_formatted_text(HTML(f"<info>--- End of List ---</info>"), style=style)
                except Exception as e:
                    print_formatted_text(HTML(f"<error>❌ Error: {e}</error>"), style=style)

            # --- CHATS COMMAND ---
            elif msg_clean.startswith('/chats'):
                filter_type = None
                target_count = 10
                args = cmd[1:]
                for arg in args:
                    if arg.isdigit():
                        target_count = int(arg)
                    elif arg.lower() in ['users', 'user']:
                        filter_type = 'user'
                    elif arg.lower() in ['groups', 'group']:
                        filter_type = 'group'
                    elif arg.lower() in ['channels', 'channel']:
                        filter_type = 'channel'

                print_formatted_text(HTML(f"<system>⏳ Fetching recent chats...</system>"), style=style)
                try:
                    chat_list_cache = [] 
                    count_found = 0
                    print_formatted_text(HTML(f"<info>--- Recent Chats ---</info>"), style=style)
                    async for dialog in client.iter_dialogs():
                        entity = dialog.entity
                        is_user = dialog.is_user
                        is_group = dialog.is_group
                        is_channel = dialog.is_channel
                        
                        if filter_type:
                            if filter_type == 'user' and not is_user: continue
                            if filter_type == 'group' and not is_group: continue
                            if filter_type == 'channel' and not is_channel: continue

                        chat_list_cache.append(entity)
                        count_found += 1
                        
                        name = get_display_name(entity)
                        type_label = "User" if is_user else "Group" if is_group else "Channel" if is_channel else "Unknown"
                        unread_str = f" <unread>({dialog.unread_count} unread)</unread>" if dialog.unread_count > 0 else ""
                        print_formatted_text(HTML(f"<plain>[{count_found}] <type>[{type_label}]</type> <b>{html.escape(name)}</b>{unread_str}</plain>"), style=style)
                        
                        if count_found >= target_count:
                            break
                    print_formatted_text(HTML(f"<info>---------------------</info>"), style=style)
                    print_formatted_text(HTML(f"<system>Use '/c [n]' to select a chat.</system>"), style=style)
                except Exception as e:
                    print_formatted_text(HTML(f"<error>❌ Error: {e}</error>"), style=style)

            # --- JUMP TO CHAT (/c [n]) ---
            elif msg_clean.startswith('/c '):
                try:
                    idx = int(cmd[1]) - 1
                    if 0 <= idx < len(chat_list_cache):
                        entity = chat_list_cache[idx]
                        current_chat = ChatSession(entity)
                        today = datetime.now()
                        print_formatted_text(HTML(f"<date>  📅 Today: {today.strftime('%A, %B %d, %Y')}  </date>"), style=style)
                        current_chat.last_message_date = today.date()
                        
                        status_str = ""
                        try:
                            if isinstance(entity, User):
                                full_entity = await client.get_entity(entity.id)
                                s = get_user_status(full_entity)
                                if s: status_str = f" ({s})"
                        except: pass
                        
                        print_formatted_text(HTML(f"<system>✅ Switched chat to: {html.escape(current_chat.name)}{status_str}</system>"), style=style)
                        def_hist = user_settings.get("defaultHistory", 0)
                        if def_hist > 0:
                            await fetch_and_render_history(def_hist)
                    else:
                        print_formatted_text(HTML(f"<error>❌ Invalid index or list expired. Run /chats again.</error>"), style=style)
                except (IndexError, ValueError):
                    print_formatted_text(HTML(f"<error>❌ Usage: /c [number]</error>"), style=style)

            # --- UNREAD COMMAND ---
            elif msg_clean.startswith('/unread'):
                limit = 10 if 'all' not in msg_clean else None
                print_formatted_text(HTML(f"<system>⏳ Scanning for unread messages...</system>"), style=style)
                count = 0
                try:
                    async for dialog in client.iter_dialogs(limit=100):
                        if dialog.unread_count > 0:
                            name = get_display_name(dialog.entity)
                            print_formatted_text(HTML(f"<plain>• <b>{html.escape(name)}</b> <unread>({dialog.unread_count} unread)</unread></plain>"), style=style)
                            count += 1
                            if limit and count >= limit: break
                    if count == 0:
                        print_formatted_text(HTML("<system>🎉 No unread messages found in recent chats.</system>"), style=style)
                except Exception as e:
                      print_formatted_text(HTML(f"<error>❌ Error: {e}</error>"), style=style)

            # --- RECIPIENT COMMAND ---
            elif msg_clean.startswith('/recipient') or msg_clean.startswith('/r '):
                target_input = " ".join(cmd[1:]) if len(cmd) > 1 else None
                if not target_input:
                    with patch_stdout():
                        target_input = await session.prompt_async(HTML("<system>Enter name or @username: </system>"))
                
                if target_input:
                    try:
                        print_formatted_text(HTML(f"<system>🔍 Searching for '{html.escape(target_input)}'...</system>"), style=style)
                        new_entity = None
                        if target_input.startswith("@") or target_input.startswith("+"):
                            try: new_entity = await client.get_entity(target_input)
                            except: pass
                        if not new_entity:
                            async for dialog in client.iter_dialogs():
                                if get_display_name(dialog.entity).lower() == target_input.lower():
                                    new_entity = dialog.entity
                                    break
                                if getattr(dialog.entity, 'username', '') and dialog.entity.username.lower() == target_input.lower().replace("@", ""):
                                    new_entity = dialog.entity
                                    break
                        if not new_entity:
                             async for dialog in client.iter_dialogs(limit=100):
                                if target_input.lower() in get_display_name(dialog.entity).lower():
                                    new_entity = dialog.entity
                                    break

                        if new_entity:
                            current_chat = ChatSession(new_entity)
                            today = datetime.now()
                            print_formatted_text(HTML(f"<date>  📅 Today: {today.strftime('%A, %B %d, %Y')}  </date>"), style=style)
                            current_chat.last_message_date = today.date()
                            
                            status_str = ""
                            try:
                                if isinstance(new_entity, User):
                                    full_entity = await client.get_entity(new_entity.id)
                                    s = get_user_status(full_entity)
                                    if s: status_str = f" ({s})"
                            except: pass

                            print_formatted_text(HTML(f"<system>✅ Switched chat to: {html.escape(current_chat.name)}{status_str}</system>"), style=style)
                            def_hist = user_settings.get("defaultHistory", 0)
                            if def_hist > 0:
                                await fetch_and_render_history(def_hist)
                        else:
                            print_formatted_text(HTML(f"<error>❌ Could not find user '{html.escape(target_input)}'.</error>"), style=style)
                            print_formatted_text(HTML(f"<info>ℹ️  Please use: @username, +Phone, or Exact Name.</info>"), style=style)
                    except Exception as e:
                         print_formatted_text(HTML(f"<error>❌ Connection Error: {e}</error>"), style=style)

            # --- HISTORY COMMAND ---
            elif msg_clean.startswith('/history') or msg_clean.startswith('/h ') or msg_clean == '/h':
                limit = min(int(cmd[1]), 500) if len(cmd) > 1 and cmd[1].isdigit() else 20
                if current_chat: await fetch_and_render_history(limit)
                else: print_formatted_text(HTML(f"<error>❌ No active chat.</error>"), style=style)

            # --- SEND MESSAGE ---
            elif msg_clean:
                if current_chat:
                    now = datetime.now()
                    if current_chat.last_message_date != now.date():
                        date_str = now.strftime("%A, %B %d, %Y")
                        print_formatted_text(HTML(f"<date>  📅 {date_str}  </date>"), style=style)
                        current_chat.last_message_date = now.date()

                    try:
                        reply_to = current_chat.reply_to_msg_id
                        sent_msg = await client.send_message(current_chat.entity, msg_clean, reply_to=reply_to)
                        with patch_stdout():
                            now_str = now.strftime('%H:%M')
                            safe_msg = html.escape(msg_clean)
                            reply_label = " (reply)" if reply_to else ""
                            idx = current_chat.next_index
                            current_chat.message_index_map[idx] = sent_msg
                            current_chat.next_index += 1
                            print_formatted_text(HTML(f"<sent><index>[{idx}]</index> [{now_str}] [You]{reply_label}: {safe_msg}</sent>"), style=style)
                        if reply_to:
                            current_chat.reply_to_msg_id = None
                            current_chat.reply_snippet = None
                    except Exception as e:
                         print_formatted_text(HTML(f"<error>❌ Failed to send: {e}</error>"), style=style)
                else:
                     if msg_clean.startswith("@"):
                         print_formatted_text(HTML(f"<error>❌ No recipient selected! Use '/r {html.escape(msg_clean)}' to chat.</error>"), style=style)
                     else:
                         print_formatted_text(HTML(f"<error>❌ No recipient selected! Use /r [name] or /chats to start.</error>"), style=style)
                
        except (KeyboardInterrupt, EOFError):
            break

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())