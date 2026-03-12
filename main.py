import os
import random
import time
import re
from dotenv import load_dotenv
import google.generativeai as genai
from moviepy.editor import ImageClip, CompositeVideoClip, AudioFileClip, afx
from PIL import Image, ImageDraw, ImageFont

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ==================== CONFIG ====================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

QUOTES_FILE = "quotes.txt"
OUTPUT_FILE = "viral_short.mp4"
VIDEO_SIZE = (1080, 1920)

CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

FONT_REGULAR_PATH = "arial.ttf"
FONT_BOLD_PATH = "arialbd.ttf"
FONT_SIZE = 50
LEFT_MARGIN = 120
RIGHT_MARGIN = 120
LINE_SPACING = 30
PARAGRAPH_SPACING = 50

FADE_IN = 0.5
HOLD_DURATION = 3.0
FADE_OUT = 0.0

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ==================== QUOTE FILE MANAGEMENT ====================

def get_next_quote():
    """quotes.txt se pehla quote uthao"""
    if not os.path.exists(QUOTES_FILE):
        print(f"❌ {QUOTES_FILE} nahi mila!")
        return None

    with open(QUOTES_FILE, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    if not content:
        print(f"❌ {QUOTES_FILE} khali hai! Quotes daalo.")
        return None

    # --- se split karo
    quotes = [q.strip() for q in content.split('---') if q.strip()]

    if not quotes:
        print("❌ Koi valid quote nahi mila!")
        return None

    # FIFO - pehla quote uthao
    quote = quotes[0]
    remaining = len(quotes) - 1

    print(f"📖 Quote loaded! ({remaining} remaining after this)")
    print(f"📝 Quote preview: {quote[:100]}...")

    return quote


def remove_used_quote():
    """Pehla quote delete karo file se"""
    with open(QUOTES_FILE, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    quotes = [q.strip() for q in content.split('---') if q.strip()]

    if quotes:
        used = quotes.pop(0)
        print(f"🗑️ Removed: {used[:50]}...")

    # Baaki quotes wapas likho
    if quotes:
        new_content = '\n---\n'.join(quotes) + '\n'
    else:
        new_content = ''

    with open(QUOTES_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"📊 {len(quotes)} quotes remaining in file.")


# ==================== AI METADATA GENERATION ====================

def generate_metadata(quote_text):
    """AI se sirf Title, Description, Tags banwao — quote NAHI"""
    print("🤖 AI generating metadata (title/desc/tags)...")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # AI ko clean quote do (bina ** ke)
    clean_quote = quote_text.replace('**', '')

    prompt = f"""
You are managing a YouTube Shorts channel called "BILLIONAIRE MINDSET".
The channel posts motivational quote videos.

Here is the EXACT quote that will appear in the video:
"{clean_quote}"

Your job: Generate ONLY the metadata for this YouTube Short.
DO NOT change or rewrite the quote. Just create metadata FOR it.

Rules:
1. TITLE: Catchy, under 100 characters, 2-3 emojis, MUST include #shorts
   - Make someone STOP scrolling
   - Feel urgent and personal
   - Don't reveal the full quote in title

2. DESCRIPTION: 2-4 short engaging lines + 5-6 hashtags including #shorts
   - Relatable and engaging
   - Include relevant hashtags

3. TAGS: 25-30 comma-separated SEO keywords
   - Include: motivation, shorts, mindset + topic-relevant words

OUTPUT FORMAT (FOLLOW EXACTLY):
TITLE: [your title]
DESCRIPTION: [your description]
TAGS: [your tags]
"""

    # Default fallback agar AI fail ho
    defaults = {
        "TITLE": "This Will Change Your Mindset 🔥💯 #shorts",
        "DESCRIPTION": "A reminder you needed today.\n#shorts #motivation #mindset #growth #discipline",
        "TAGS": "motivation, mindset, growth, discipline, success, hustle, shorts, self improvement, viral, billionaire mindset"
    }

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        print(f"\n📋 AI Raw Response:\n{text}\n")

        data = defaults.copy()
        current_key = None

        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue

            # Clean markdown
            stripped = stripped.replace('**', '').replace('##', '')
            upper = stripped.upper()

            if upper.startswith('TITLE'):
                current_key = 'TITLE'
                if ':' in stripped:
                    val = stripped.split(':', 1)[1].strip().strip('"').strip("'")
                    if val:
                        data['TITLE'] = val
            elif upper.startswith('DESCRIPTION'):
                current_key = 'DESCRIPTION'
                if ':' in stripped:
                    val = stripped.split(':', 1)[1].strip().strip('"').strip("'")
                    if val:
                        data['DESCRIPTION'] = val
            elif upper.startswith('TAG'):
                current_key = 'TAGS'
                if ':' in stripped:
                    val = stripped.split(':', 1)[1].strip().strip('"').strip("'")
                    if val:
                        data['TAGS'] = val
            elif current_key == 'DESCRIPTION':
                data['DESCRIPTION'] += '\n' + stripped
            elif current_key == 'TAGS':
                data['TAGS'] += ', ' + stripped

        # Title length check
        if len(data['TITLE']) > 100:
            data['TITLE'] = data['TITLE'][:97] + '...'

        # Ensure #Shorts in description
        if '#shorts' not in data['DESCRIPTION'].lower():
            data['DESCRIPTION'] += '\n#Shorts'

        print(f"✅ Title: {data['TITLE']}")
        print(f"✅ Tags: {data['TAGS'][:80]}...")

        return data

    except Exception as e:
        print(f"⚠️ AI Error: {e}. Using defaults.")
        return defaults


# ==================== IMAGE CREATION ====================

def create_styled_image(quote_text):
    """Black background pe styled quote text ka image banao"""
    img = Image.new("RGB", VIDEO_SIZE, color="black")
    draw = ImageDraw.Draw(img)

    try:
        font_reg = ImageFont.truetype(FONT_REGULAR_PATH, FONT_SIZE)
        font_bold = ImageFont.truetype(FONT_BOLD_PATH, FONT_SIZE)
    except Exception as e:
        print(f"⚠️ Font error: {e}. Using default.")
        font_reg = ImageFont.load_default()
        font_bold = font_reg

    max_text_width = VIDEO_SIZE[0] - LEFT_MARGIN - RIGHT_MARGIN

    def render_text(draw_obj, text, start_y, execute=False):
        lines = text.split('\n')
        current_y = start_y

        bbox = font_reg.getbbox("A")
        char_h = bbox[3] - bbox[1]
        space_w = font_reg.getlength(" ")

        for line in lines:
            words = line.split(' ')
            current_x = LEFT_MARGIN

            for word in words:
                if not word:
                    continue

                is_bold = "**" in word
                clean_word = word.replace("**", "")

                font = font_bold if is_bold else font_reg
                word_w = font.getlength(clean_word)

                # Word wrap
                if current_x + word_w > LEFT_MARGIN + max_text_width:
                    current_x = LEFT_MARGIN
                    current_y += char_h + LINE_SPACING

                if execute and draw_obj:
                    draw_obj.text(
                        (current_x, current_y),
                        clean_word,
                        font=font,
                        fill="white"
                    )

                current_x += word_w + space_w

            current_y += char_h + PARAGRAPH_SPACING

        return current_y - start_y

    # Center vertically
    total_h = render_text(None, quote_text, 0, False)
    start_y = (VIDEO_SIZE[1] - total_h) / 2 - 100

    render_text(draw, quote_text, start_y, True)

    temp_path = "temp_frame.png"
    img.save(temp_path)
    return temp_path


# ==================== MUSIC ====================

def get_random_music(duration):
    """music/ folder se random track uthao"""
    music_dir = "music"
    if not os.path.exists(music_dir):
        print("⚠️ music/ folder nahi mila. No background music.")
        return None

    tracks = [
        os.path.join(music_dir, f)
        for f in os.listdir(music_dir)
        if f.lower().endswith((".mp3", ".wav"))
    ]

    if not tracks:
        print("⚠️ No music files found.")
        return None

    track = random.choice(tracks)
    print(f"🎵 Music: {os.path.basename(track)}")

    audio = AudioFileClip(track)
    if audio.duration < duration:
        audio = afx.audio_loop(audio, duration=duration)
    audio = audio.subclip(0, duration).volumex(0.25)
    return audio


# ==================== VIDEO CREATION ====================

def create_video(quote_text):
    """Quote se video banao"""
    print("🎬 Creating video...")

    img_path = create_styled_image(quote_text)

    total_duration = FADE_IN + HOLD_DURATION + FADE_OUT
    clip = ImageClip(img_path).set_duration(total_duration)
    clip = clip.fadein(FADE_IN).fadeout(FADE_OUT)
    final = CompositeVideoClip([clip], size=VIDEO_SIZE)

    music = get_random_music(total_duration)
    if music:
        final = final.set_audio(music)

    final.write_videofile(
        OUTPUT_FILE,
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    if os.path.exists(img_path):
        os.remove(img_path)

    print(f"✅ Video ready: {OUTPUT_FILE}")


# ==================== YOUTUBE AUTH & UPLOAD ====================

def authenticate_youtube():
    """YouTube API authenticate karo"""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Token expired, refreshing...")
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                print(f"❌ {CLIENT_SECRET_FILE} nahi mila!")
                return None
            print("🔐 Browser kholega for login...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
        print("✅ Token saved!")

    return build("youtube", "v3", credentials=creds)


def upload_short(file_path, metadata):
    """YouTube pe upload karo. Success pe True return."""
    try:
        youtube = authenticate_youtube()
        if not youtube:
            print("❌ Authentication fail!")
            return False

        # Tags process
        raw_tags = metadata.get("TAGS", "motivation, shorts")
        tag_list = [t.strip() for t in raw_tags.split(',') if t.strip()]
        if 'shorts' not in [t.lower() for t in tag_list]:
            tag_list.append('shorts')

        title = metadata.get("TITLE", "Motivation 🔥 #shorts")
        description = metadata.get("DESCRIPTION", "Daily motivation #shorts")

        if '#Shorts' not in description and '#shorts' not in description:
            description += '\n\n#Shorts'

        print(f"\n📋 UPLOADING WITH:")
        print(f"   Title: {title}")
        print(f"   Tags: {tag_list[:10]}...")
        print(f"   Desc: {description[:60]}...")

        request_body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tag_list,
                "categoryId": "22",
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            file_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=256 * 1024
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media
        )

        print("🚀 Uploading to YouTube...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"   📊 Upload: {int(status.progress() * 100)}%")

        video_id = response.get('id')
        print(f"✅ Upload Complete!")
        print(f"🔗 https://youtube.com/shorts/{video_id}")
        return True

    except Exception as e:
        print(f"❌ Upload Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 BILLIONAIRE MINDSET - Quote File Automator")
    print("=" * 50)

    # 1️⃣ File se next quote uthao
    quote = get_next_quote()
    if not quote:
        print("❌ No quotes available. Add quotes to quotes.txt!")
        exit(1)

    # 2️⃣ AI se sirf metadata banwao (title/desc/tags)
    metadata = generate_metadata(quote)

    # 3️⃣ Video banao
    create_video(quote)

    # 4️⃣ YouTube pe upload karo
    success = upload_short(OUTPUT_FILE, metadata)

    # 5️⃣ SIRF upload success pe quote delete karo
    if success:
        remove_used_quote()
        print("\n🎉 DONE! Quote used → video uploaded → quote removed!")
    else:
        print("\n⚠️ Upload failed. Quote file mei quote rehega for retry.")

    # 6️⃣ Cleanup
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print("🧹 Video file cleaned up.")
