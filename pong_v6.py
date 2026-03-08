"""
PONG PRO v6.0 — PRODUCTION READY
✅ Player Vs CPU
✅ Animated splash screen
✅ Username login + API profile
✅ Difficulty selector
✅ Countdown before match
✅ Procedural sound effects (no audio files needed)
✅ Game Over screen with stats + buttons
✅ Local leaderboard (leaderboard.json)
✅ Controls / key-remap screen (save.json)
"""

import pygame
import random
import math
import time
import os
import sys
import json
import requests
import array
import struct

# ══════════════════════════════════════════════════════════════════════
#  PATHS
# ══════════════════════════════════════════════════════════════════════

def resource_path(relative_path):
    """
    Resolve path to a BUNDLED read-only asset (e.g. icon, sound file).
    Points inside the PyInstaller .app bundle when frozen,
    or to the source directory during development.
    """
    try:
        base_path = sys._MEIPASS          # frozen: inside .app bundle
    except AttributeError:
        base_path = os.path.abspath(".")  # dev: next to pong_v6.py
    return os.path.join(base_path, relative_path)


def user_data_path(filename):
    """
    Resolve path for WRITABLE user data (save.json, leaderboard.json).

    Platform behaviour:
      macOS   → ~/Library/Application Support/PONG PRO/<filename>
      Windows → %APPDATA%/PONG PRO/<filename>
      Linux   → ~/.local/share/PONG PRO/<filename>
      Dev     → next to pong_v6.py (convenient during development)

    The directory is created automatically if it doesn't exist.
    """
    if getattr(sys, "frozen", False):
        # Running as a packaged .app / .exe
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/PONG PRO")
        elif sys.platform == "win32":
            base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                "PONG PRO")
        else:
            base = os.path.expanduser("~/.local/share/PONG PRO")
    else:
        # Development: keep files next to the script for easy inspection
        base = os.path.abspath(".")

    os.makedirs(base, exist_ok=True)
    return os.path.join(base, filename)


SAVE_FILE        = user_data_path("save.json")
LEADERBOARD_FILE = user_data_path("leaderboard.json")

# ══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════

WIDTH, HEIGHT        = 900, 600
FPS                  = 60
WINNING_SCORE        = 7
MAX_BALL_SPEED       = 18
BALL_INITIAL_SPEED   = 6
PADDLE_WIDTH         = 12
PADDLE_HEIGHT        = 90
BALL_SIZE            = 12
COUNTDOWN_SECONDS    = 3

# Colours
WHITE        = (245, 245, 255)
BLACK        = (10,  10,  25)
DIM          = (20,  20,  45)
NEON_BLUE    = (0,   255, 255)
NEON_PINK    = (255, 40,  150)
NEON_GREEN   = (57,  255, 20)
NEON_PURPLE  = (200, 0,   255)
NEON_ORANGE  = (255, 165, 0)
NEON_YELLOW  = (255, 255, 0)
GREY         = (120, 120, 140)

# AI speed per difficulty
AI_SPEED = {"Easy": 4.0, "Medium": 6.5, "Hard": 9.5}

# Default key bindings  (stored as pygame key constants)
DEFAULT_BINDINGS = {
    "up":    pygame.K_w,
    "down":  pygame.K_s,
    "pause": pygame.K_ESCAPE,
}

# ══════════════════════════════════════════════════════════════════════
#  PERSISTENCE HELPERS
# ══════════════════════════════════════════════════════════════════════

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Save] {e}")

# ══════════════════════════════════════════════════════════════════════
#  API CLIENT
# ══════════════════════════════════════════════════════════════════════

class APIClient:
    def __init__(self, server_url="https://pong.deewhy.ovh"):
        self.server_url = server_url

    def create_or_load_profile(self, username):
        try:
            r = requests.post(f"{self.server_url}/api/user/{username}", timeout=4)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[API] create_or_load_profile: {e}")
        return {"username": username, "total_wins": 0,
                "total_losses": 0, "total_matches": 0, "level": 1}

    def update_profile(self, username, win):
        try:
            r = requests.post(
                f"{self.server_url}/api/user/{username}/update",
                json={"win": win}, timeout=4)
            return r.status_code == 200
        except Exception as e:
            print(f"[API] update_profile: {e}")
            return False

# ══════════════════════════════════════════════════════════════════════
#  SOUND SYNTHESISER  (no audio files, no numpy — pure stdlib)
# ══════════════════════════════════════════════════════════════════════

class SoundEngine:
    """
    Procedural audio using only Python stdlib (math, array, struct) and
    pygame.mixer.  Generates signed-16-bit mono PCM samples via math.sin,
    wraps them in a minimal WAV buffer, and loads with pygame.mixer.Sound.
    All sounds are cached after first generation so there is zero per-frame
    allocation cost.
    """
    SAMPLE_RATE = 44100

    def __init__(self):
        pygame.mixer.pre_init(self.SAMPLE_RATE, -16, 1, 512)
        pygame.mixer.init()
        self.enabled = True
        self._cache: dict = {}

    # ── internal builders ──────────────────────────────────────────────

    def _build_wav(self, samples_i16: array.array) -> bytes:
        """Wrap a signed-16-bit sample array in a minimal WAV byte string."""
        num_samples  = len(samples_i16)
        data_size    = num_samples * 2          # 2 bytes per int16
        byte_rate    = self.SAMPLE_RATE * 2
        block_align  = 2
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,     # overall file size - 8
            b"WAVE",
            b"fmt ",
            16,                 # chunk size
            1,                  # PCM
            1,                  # mono
            self.SAMPLE_RATE,
            byte_rate,
            block_align,
            16,                 # bits per sample
            b"data",
            data_size,
        )
        return header + samples_i16.tobytes()

    def _sine(self, freq: float, duration: float,
              volume: float = 0.5, decay: bool = True) -> pygame.mixer.Sound:
        key = ("sine", round(freq), round(duration * 1000), round(volume * 100), decay)
        if key in self._cache:
            return self._cache[key]

        n       = int(self.SAMPLE_RATE * duration)
        peak    = 32767 * volume
        two_pi_f = 2.0 * math.pi * freq
        buf     = array.array("h", [0] * n)

        for i in range(n):
            t         = i / self.SAMPLE_RATE
            sine_val  = math.sin(two_pi_f * t)
            env       = ((n - i) / n) ** 1.5 if decay else 1.0
            buf[i]    = int(max(-32767, min(32767, sine_val * env * peak)))

        wav   = self._build_wav(buf)
        import io
        sound = pygame.mixer.Sound(file=io.BytesIO(wav))
        self._cache[key] = sound
        return sound

    # ── public API ─────────────────────────────────────────────────────

    def play_paddle_hit(self, diff_fraction: float = 0.0):
        """Short sharp click; pitch varies with hit position on paddle."""
        if not self.enabled:
            return
        freq = 480 + int(diff_fraction * 220)   # 480–700 Hz
        self._sine(freq, 0.07, volume=0.55).play()

    def play_wall_bounce(self):
        if not self.enabled:
            return
        self._sine(220, 0.06, volume=0.35).play()

    def play_score(self, player_scored: bool):
        """Ascending two-tone blip for scorer, descending for loser."""
        if not self.enabled:
            return
        if player_scored:
            self._sine(440, 0.08, volume=0.5).play()
            pygame.time.delay(90)
            self._sine(660, 0.12, volume=0.5).play()
        else:
            self._sine(330, 0.08, volume=0.5).play()
            pygame.time.delay(90)
            self._sine(220, 0.14, volume=0.5).play()

    def play_countdown_tick(self):
        if not self.enabled:
            return
        self._sine(660, 0.1, volume=0.4).play()

    def play_countdown_go(self):
        if not self.enabled:
            return
        self._sine(880, 0.18, volume=0.6).play()

    def play_game_over(self, player_won: bool):
        if not self.enabled:
            return
        if player_won:
            for freq in [440, 550, 660, 880]:
                self._sine(freq, 0.1, volume=0.55).play()
                pygame.time.delay(110)
        else:
            for freq in [440, 330, 220]:
                self._sine(freq, 0.14, volume=0.5).play()
                pygame.time.delay(130)

# ══════════════════════════════════════════════════════════════════════
#  PARTICLE
# ══════════════════════════════════════════════════════════════════════

class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        self.vx = random.uniform(-2, 2)
        self.vy = random.uniform(-2, 2)
        self.life  = 1.0
        self.color = color

    def update(self):
        self.x    += self.vx
        self.y    += self.vy
        self.life -= 0.03

    def draw(self, surface, ox, oy):
        if self.life <= 0:
            return
        alpha = max(0, min(255, int(self.life * 255)))
        size  = int(self.life * 4) + 1
        s     = pygame.Surface((size, size), pygame.SRCALPHA)
        s.fill((*self.color, alpha))
        surface.blit(s, (self.x + ox, self.y + oy))

# ══════════════════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════════════════

def draw_button(surface, rect, label, font, hover,
                color_active=NEON_BLUE, color_idle=None):
    """Draw a standard neon button. Returns True if mouse is hovering."""
    if color_idle is None:
        color_idle = (color_active[0]//3, color_active[1]//3, color_active[2]//3)
    bg = (40, 45, 80) if hover else (25, 28, 55)
    pygame.draw.rect(surface, bg,              rect, border_radius=10)
    pygame.draw.rect(surface, color_active if hover else color_idle,
                     rect, 2 if not hover else 3, border_radius=10)
    txt = font.render(label, True, color_active if hover else WHITE)
    surface.blit(txt, (rect.centerx - txt.get_width()//2,
                        rect.centery - txt.get_height()//2))
    return hover

# ══════════════════════════════════════════════════════════════════════
#  LEADERBOARD
# ══════════════════════════════════════════════════════════════════════

class Leaderboard:
    MAX_ENTRIES = 10

    def __init__(self):
        raw = load_json(LEADERBOARD_FILE, [])
        self.entries = raw if isinstance(raw, list) else []

    def record(self, username, won):
        """Update or insert entry for username."""
        entry = next((e for e in self.entries if e["name"] == username), None)
        if entry is None:
            entry = {"name": username, "wins": 0, "losses": 0}
            self.entries.append(entry)
        if won:
            entry["wins"] += 1
        else:
            entry["losses"] += 1
        self._sort_and_trim()
        save_json(LEADERBOARD_FILE, self.entries)

    def _sort_and_trim(self):
        def rate(e):
            total = e["wins"] + e["losses"]
            return e["wins"] / total if total else 0
        self.entries.sort(key=lambda e: (e["wins"], rate(e)), reverse=True)
        self.entries = self.entries[:self.MAX_ENTRIES]

    def top(self):
        return self.entries

# ══════════════════════════════════════════════════════════════════════
#  MAIN GAME
# ══════════════════════════════════════════════════════════════════════

class PongPro:

    # ── init ───────────────────────────────────────────────────────────

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (WIDTH, HEIGHT), pygame.DOUBLEBUF | pygame.HWSURFACE)
        pygame.display.set_caption("PONG PRO v6.0")
        self.clock  = pygame.time.Clock()
        self.sounds = SoundEngine()

        # Fonts
        self.font_huge   = pygame.font.SysFont("Arial",    72, bold=True)
        self.font_main   = pygame.font.SysFont("Arial",    48, bold=True)
        self.font_medium = pygame.font.SysFont("Arial",    32, bold=True)
        self.font_small  = pygame.font.SysFont("Arial",    24, bold=True)
        self.font_ui     = pygame.font.SysFont("Monospace",18)
        self.font_tiny   = pygame.font.SysFont("Monospace",14)

        # Persistence
        self.api         = APIClient()
        self.leaderboard = Leaderboard()
        save             = load_json(SAVE_FILE, {})
        self.bindings    = save.get("bindings", dict(DEFAULT_BINDINGS))
        self.last_username = save.get("username", "")

        # State machine
        # SPLASH → LOGIN → MENU → COUNTDOWN → GAME → END
        # MENU ←→ LEADERBOARD
        # MENU ←→ CONTROLS
        self.state = "SPLASH"

        # Splash
        self.splash_timer   = 0.0
        self.splash_duration = 2.2   # seconds

        # Login
        self.temp_username = self.last_username
        self.login_error   = ""
        self.login_loading = False

        # Profile
        self.username = ""
        self.profile  = None

        # Menu
        self.difficulty = save.get("difficulty", "Medium")

        # Countdown
        self.countdown_start = 0.0
        self.countdown_last  = -1

        # Game
        self.paused        = False
        self.stats_saved   = False
        self.p1_score      = 0
        self.p2_score      = 0
        self.p1_y          = HEIGHT // 2 - PADDLE_HEIGHT // 2
        self.p2_y          = HEIGHT // 2 - PADDLE_HEIGHT // 2
        self.ball_x        = WIDTH  // 2
        self.ball_y        = HEIGHT // 2
        self.ball_vx       = BALL_INITIAL_SPEED
        self.ball_vy       = 0.0
        self.stats         = {"rally":0,"max_rally":0,"total_hits":0,
                               "start_time":0,"duration":0}

        # Controls remap
        self.remap_target  = None   # key name being remapped

        # Quit confirmation overlay (shown on menu ESC)
        self.quit_confirm  = False

        # End screen
        self.end_player_won = False

        # Visual effects
        self.particles      = []
        self.stars          = [
            (random.randint(0,WIDTH), random.randint(0,HEIGHT), random.uniform(0.5,2.5))
            for _ in range(150)]
        self.nebula_timer   = 0.0
        self.shake_intensity = 0.0
        self.shake_decay    = 0.85

        # Pre-render vignette
        self.vignette_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for r in range(WIDTH, 0, -15):
            alpha = int(min(160, (r / WIDTH) ** 2 * 180))
            pygame.draw.circle(
                self.vignette_surf, (0,0,10,alpha), (WIDTH//2,HEIGHT//2), r)

    # ── persistence ───────────────────────────────────────────────────

    def _save_prefs(self):
        save_json(SAVE_FILE, {
            "username":   self.username,
            "bindings":   self.bindings,
            "difficulty": self.difficulty,
        })

    # ── visual helpers ────────────────────────────────────────────────

    def trigger_shake(self, intensity):
        self.shake_intensity = intensity

    def draw_background(self, ox=0, oy=0):
        self.screen.fill((15, 15, 35))
        self.nebula_timer += 0.01
        for x, y, speed in self.stars:
            mx = (x + self.nebula_timer * speed * 12) % WIDTH
            br = int(190 + 65 * math.sin(self.nebula_timer + x))
            pygame.draw.circle(
                self.screen, (br,br,br), (int(mx+ox), int(y+oy)), 1)
        pulse = abs(math.sin(time.time() * 3)) * 60
        dc    = (70, 70, int(140+pulse))
        for y in range(0, HEIGHT, 40):
            pygame.draw.rect(
                self.screen, dc, (WIDTH//2-2+ox, y+10+oy, 4, 20))

    def draw_vignette(self):
        self.screen.blit(self.vignette_surf, (0,0))

    def _scanlines(self, alpha=18):
        """Subtle scanline overlay for retro feel."""
        for y in range(0, HEIGHT, 3):
            pygame.draw.line(self.screen, (0,0,0,alpha), (0,y), (WIDTH,y))

    # ── game object helpers ───────────────────────────────────────────

    def reset_game_objects(self):
        self.p1_y = self.p2_y = HEIGHT//2 - PADDLE_HEIGHT//2
        self.ball_x, self.ball_y = WIDTH//2, HEIGHT//2
        self.ball_vx = random.choice([-BALL_INITIAL_SPEED, BALL_INITIAL_SPEED])
        self.ball_vy = random.uniform(-3, 3)
        self.p1_score = self.p2_score = 0
        self.stats = {"rally":0,"max_rally":0,"total_hits":0,
                      "start_time":time.time(),"duration":0}
        self.stats_saved = False
        self.particles.clear()

    def reset_ball(self):
        self.ball_x, self.ball_y = WIDTH//2, HEIGHT//2
        self.ball_vx = random.choice([-BALL_INITIAL_SPEED, BALL_INITIAL_SPEED])
        self.ball_vy = random.uniform(-3, 3)

    def check_rally(self):
        if self.stats["rally"] > self.stats["max_rally"]:
            self.stats["max_rally"] = self.stats["rally"]
        self.stats["rally"] = 0

    # ── AI ────────────────────────────────────────────────────────────

    def handle_ai(self):
        target_y = self.ball_y - PADDLE_HEIGHT // 2
        speed    = AI_SPEED[self.difficulty]
        if self.ball_vx > 0:
            if abs(self.p2_y - target_y) > 10:
                self.p2_y += speed if self.p2_y < target_y else -speed
        else:
            centre = HEIGHT//2 - PADDLE_HEIGHT//2
            if abs(self.p2_y - centre) > 10:
                self.p2_y += speed*0.4 if self.p2_y < centre else -speed*0.4
        self.p2_y = max(0, min(HEIGHT - PADDLE_HEIGHT, self.p2_y))

    # ── physics ───────────────────────────────────────────────────────

    def update_physics(self):
        prev_x = self.ball_x
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        self.shake_intensity *= self.shake_decay
        if self.shake_intensity < 0.2:
            self.shake_intensity = 0

        if random.random() > 0.3:
            c = NEON_BLUE if self.ball_vx < 0 else NEON_PINK
            self.particles.append(Particle(self.ball_x, self.ball_y, c))

        # Wall bounce
        if self.ball_y <= 0 or self.ball_y >= HEIGHT - BALL_SIZE:
            self.ball_vy *= -1
            self.trigger_shake(4)
            self.sounds.play_wall_bounce()
            for _ in range(5):
                self.particles.append(Particle(self.ball_x, self.ball_y, WHITE))

        # Left paddle
        p1r = 40
        if self.ball_vx < 0 and prev_x >= p1r and self.ball_x <= p1r:
            if self.p1_y - BALL_SIZE < self.ball_y < self.p1_y + PADDLE_HEIGHT:
                self.ball_x  = p1r
                spd          = min(abs(self.ball_vx) * 1.06, MAX_BALL_SPEED)
                self.ball_vx = spd
                diff         = (self.ball_y - (self.p1_y + PADDLE_HEIGHT/2)) / (PADDLE_HEIGHT/2)
                self.ball_vy = diff * 8
                self.trigger_shake(12)
                self.stats["rally"]      += 1
                self.stats["total_hits"] += 1
                self.sounds.play_paddle_hit(abs(diff))
                for _ in range(12):
                    self.particles.append(Particle(self.ball_x, self.ball_y, NEON_BLUE))

        # Right paddle
        p2l = WIDTH - 40 - BALL_SIZE
        if self.ball_vx > 0 and prev_x <= p2l and self.ball_x >= p2l:
            if self.p2_y - BALL_SIZE < self.ball_y < self.p2_y + PADDLE_HEIGHT:
                self.ball_x  = p2l
                spd          = min(abs(self.ball_vx) * 1.06, MAX_BALL_SPEED)
                self.ball_vx = -spd
                diff         = (self.ball_y - (self.p2_y + PADDLE_HEIGHT/2)) / (PADDLE_HEIGHT/2)
                self.ball_vy = diff * 8
                self.trigger_shake(12)
                self.stats["rally"]      += 1
                self.stats["total_hits"] += 1
                self.sounds.play_paddle_hit(abs(diff))
                for _ in range(12):
                    self.particles.append(Particle(self.ball_x, self.ball_y, NEON_PINK))

        # Score
        if self.ball_x < 0:
            self.p2_score += 1
            self.trigger_shake(20)
            self.check_rally()
            self.sounds.play_score(player_scored=False)
            self.reset_ball()
        elif self.ball_x > WIDTH:
            self.p1_score += 1
            self.trigger_shake(20)
            self.check_rally()
            self.sounds.play_score(player_scored=True)
            self.reset_ball()

        # Game over
        if self.p1_score >= WINNING_SCORE or self.p2_score >= WINNING_SCORE:
            self.stats["duration"] = int(time.time() - self.stats["start_time"])
            self.end_player_won    = (self.p1_score >= WINNING_SCORE)
            self.sounds.play_game_over(self.end_player_won)
            self.state = "END"

        self.particles = [p for p in self.particles if p.life > 0]

    # ══════════════════════════════════════════════════════════════════
    #  DRAW STATES
    # ══════════════════════════════════════════════════════════════════

    # ── SPLASH ────────────────────────────────────────────────────────

    def draw_splash(self):
        t = self.splash_timer
        # Background
        self.screen.fill((8, 8, 20))
        for x, y, speed in self.stars:
            mx = (x + t * speed * 8) % WIDTH
            br = int(160 + 60 * math.sin(t + x))
            pygame.draw.circle(self.screen, (br,br,br), (int(mx), int(y)), 1)

        # Fade-in alpha
        progress = min(1.0, t / 1.0)
        fade     = min(1.0, (self.splash_duration - t) / 0.5)   # fade out last 0.5s
        alpha    = int(min(progress, fade) * 255)

        # Animated neon glow behind title
        glow_r = int(80 + 30 * math.sin(t * 3))
        glow_s = pygame.Surface((500, 160), pygame.SRCALPHA)
        for r in range(80, 0, -8):
            a = int(alpha * 0.18 * (r/80))
            pygame.draw.ellipse(glow_s, (*NEON_BLUE, a), (250-r*3, 80-r, r*6, r*2))
        self.screen.blit(glow_s, (WIDTH//2-250, HEIGHT//2-80))

        # Title letters
        title_surf = self.font_huge.render("PONG PRO", True, WHITE)
        title_surf.set_alpha(alpha)
        self.screen.blit(title_surf,
            (WIDTH//2 - title_surf.get_width()//2, HEIGHT//2 - 55))

        # Subtitle pulse
        sub_alpha = int(alpha * abs(math.sin(t * 2.5)))
        sub_surf  = self.font_small.render("v6.0", True, NEON_BLUE)
        sub_surf.set_alpha(sub_alpha)
        self.screen.blit(sub_surf,
            (WIDTH//2 - sub_surf.get_width()//2, HEIGHT//2 + 20))

        # "Loading…" bottom
        if t > 0.8:
            ld = self.font_tiny.render("Loading…", True, GREY)
            ld.set_alpha(alpha)
            self.screen.blit(ld, (WIDTH//2 - ld.get_width()//2, HEIGHT - 50))

        self.draw_vignette()

    # ── LOGIN ─────────────────────────────────────────────────────────

    def draw_login(self):
        self.draw_background()

        # Card
        box = pygame.Rect(WIDTH//2 - 240, HEIGHT//2 - 150, 480, 300)
        pygame.draw.rect(self.screen, (25,28,55), box, border_radius=18)
        pygame.draw.rect(self.screen, NEON_BLUE, box, 2, border_radius=18)

        title = self.font_medium.render("ENTER YOUR NAME", True, NEON_BLUE)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, box.y + 28))

        # Input field
        inp_rect = pygame.Rect(box.x+40, box.y+100, box.width-80, 50)
        pygame.draw.rect(self.screen, (15,18,40), inp_rect, border_radius=8)
        pulse_col = (
            int(0   + 80*abs(math.sin(time.time()*2))),
            int(180 + 75*abs(math.sin(time.time()*2))),
            int(200 + 55*abs(math.sin(time.time()*2))),
        )
        pygame.draw.rect(self.screen, pulse_col, inp_rect, 2, border_radius=8)

        display = self.temp_username + (
            "|" if int(time.time()*2) % 2 == 0 else " ")
        inp_txt = self.font_small.render(display, True, WHITE)
        self.screen.blit(inp_txt, (inp_rect.x+12, inp_rect.y+12))

        # Error
        if self.login_error:
            err = self.font_tiny.render(self.login_error, True, NEON_PINK)
            self.screen.blit(err, (WIDTH//2 - err.get_width()//2, box.y+165))

        # Play button
        btn = pygame.Rect(WIDTH//2-100, box.y+210, 200, 48)
        hover = btn.collidepoint(pygame.mouse.get_pos())
        label = "Loading…" if self.login_loading else "PLAY  ▶"
        draw_button(self.screen, btn, label, self.font_small, hover, NEON_GREEN)

        hint = self.font_tiny.render("Press ENTER or click PLAY", True, GREY)
        self.screen.blit(hint, (WIDTH//2 - hint.get_width()//2, box.bottom + 14))

        self.draw_vignette()

    # ── MENU ──────────────────────────────────────────────────────────

    def draw_menu(self):
        self.draw_background()

        # Profile badge top-left
        if self.profile:
            badge = (f"  {self.profile.get('username','')}  "
                     f"Lv.{self.profile.get('level',1)}  "
                     f"{self.profile.get('total_wins',0)}W")
            bs = self.font_tiny.render(badge, True, BLACK)
            br = pygame.Rect(14, 12, bs.get_width()+12, bs.get_height()+8)
            pygame.draw.rect(self.screen, NEON_GREEN, br, border_radius=8)
            self.screen.blit(bs, (br.x+6, br.y+4))

        # Title
        title = self.font_main.render("PONG PRO", True, WHITE)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))
        sub = self.font_tiny.render("v6.0  —  Player VS CPU", True, GREY)
        self.screen.blit(sub, (WIDTH//2 - sub.get_width()//2, 138))

        mouse = pygame.mouse.get_pos()

        # ── Difficulty selector ──────────────────────────────────────
        diff_label = self.font_ui.render("DIFFICULTY", True, GREY)
        self.screen.blit(diff_label, (WIDTH//2 - diff_label.get_width()//2, 188))

        diffs = ["Easy", "Medium", "Hard"]
        diff_colors = {"Easy": NEON_GREEN, "Medium": NEON_YELLOW, "Hard": NEON_PINK}
        total_w  = len(diffs) * 120 + (len(diffs)-1) * 12
        start_x  = WIDTH//2 - total_w//2
        self._diff_rects = {}
        for i, d in enumerate(diffs):
            r = pygame.Rect(start_x + i*132, 214, 120, 40)
            self._diff_rects[d] = r
            selected = (d == self.difficulty)
            col = diff_colors[d]
            bg  = (col[0]//4, col[1]//4, col[2]//4) if selected else (20,22,45)
            pygame.draw.rect(self.screen, bg, r, border_radius=8)
            border_w = 3 if selected else 1
            pygame.draw.rect(self.screen, col if selected else GREY,
                             r, border_w, border_radius=8)
            lbl = self.font_tiny.render(d, True, col if selected else GREY)
            self.screen.blit(lbl, (r.centerx - lbl.get_width()//2,
                                    r.centery - lbl.get_height()//2))

        # ── Play button ───────────────────────────────────────────────
        play_rect = pygame.Rect(WIDTH//2 - 160, 290, 320, 60)
        hover_play = play_rect.collidepoint(mouse)
        draw_button(self.screen, play_rect, "▶  PLAY", self.font_medium,
                    hover_play, NEON_BLUE)

        # ── Secondary buttons ─────────────────────────────────────────
        btn_w, btn_h = 180, 44
        gap          = 20
        total_sec    = btn_w * 2 + gap
        bx           = WIDTH//2 - total_sec//2
        by           = 378

        lb_rect = pygame.Rect(bx, by, btn_w, btn_h)
        ct_rect = pygame.Rect(bx + btn_w + gap, by, btn_w, btn_h)

        self._lb_rect = lb_rect
        self._ct_rect = ct_rect

        draw_button(self.screen, lb_rect, "🏆 LEADERBOARD",
                    self.font_tiny, lb_rect.collidepoint(mouse), NEON_ORANGE)
        draw_button(self.screen, ct_rect, "⌨  CONTROLS",
                    self.font_tiny, ct_rect.collidepoint(mouse), NEON_PURPLE)

        # ── Quit hint ─────────────────────────────────────────────────
        quit_hint = self.font_tiny.render("ESC — Quit", True, GREY)
        self.screen.blit(quit_hint, (WIDTH//2 - quit_hint.get_width()//2,
                                      HEIGHT - 28))

        # Store rects for click handling
        self._play_rect = play_rect
        self.draw_vignette()

        # Quit confirmation modal drawn on top if active
        if self.quit_confirm:
            self.draw_quit_confirm()

    # ── COUNTDOWN ─────────────────────────────────────────────────────

    def draw_countdown(self):
        ox = random.uniform(-self.shake_intensity, self.shake_intensity)
        oy = random.uniform(-self.shake_intensity, self.shake_intensity)
        self._draw_game_scene(ox, oy)

        elapsed = time.time() - self.countdown_start
        remaining = COUNTDOWN_SECONDS - int(elapsed)

        # Tick sound
        if remaining != self.countdown_last and remaining > 0:
            self.countdown_last = remaining
            self.sounds.play_countdown_tick()
        elif remaining <= 0 and self.countdown_last != 0:
            self.countdown_last = 0
            self.sounds.play_countdown_go()

        # Overlay
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,100))
        self.screen.blit(overlay, (0,0))

        if remaining > 0:
            scale = 1.0 + 0.4 * (1.0 - (elapsed % 1.0))
            raw   = self.font_huge.render(str(remaining), True, NEON_YELLOW)
            sw    = int(raw.get_width()  * scale)
            sh    = int(raw.get_height() * scale)
            scaled= pygame.transform.smoothscale(raw, (max(1,sw), max(1,sh)))
            scaled.set_alpha(220)
            self.screen.blit(scaled,
                (WIDTH//2  - scaled.get_width()//2,
                 HEIGHT//2 - scaled.get_height()//2))
        else:
            go = self.font_huge.render("GO!", True, NEON_GREEN)
            self.screen.blit(go,
                (WIDTH//2 - go.get_width()//2,
                 HEIGHT//2 - go.get_height()//2))
            if elapsed > COUNTDOWN_SECONDS + 0.35:
                self.state = "GAME"

        self.draw_vignette()

    # ── GAME ──────────────────────────────────────────────────────────

    def _draw_game_scene(self, ox, oy):
        self.draw_background(ox, oy)
        for p in self.particles:
            p.update()
            p.draw(self.screen, ox, oy)

        p1r = pygame.Rect(20+ox, self.p1_y+oy, PADDLE_WIDTH, PADDLE_HEIGHT)
        p2r = pygame.Rect(WIDTH-20-PADDLE_WIDTH+ox, self.p2_y+oy, PADDLE_WIDTH, PADDLE_HEIGHT)
        pygame.draw.rect(self.screen, (0,100,100), p1r.inflate(4,4), border_radius=6)
        pygame.draw.rect(self.screen, NEON_BLUE,   p1r, border_radius=5)
        pygame.draw.rect(self.screen, (100,0,50),  p2r.inflate(4,4), border_radius=6)
        pygame.draw.rect(self.screen, NEON_PINK,   p2r, border_radius=5)

        pygame.draw.circle(self.screen, WHITE,
            (int(self.ball_x+ox), int(self.ball_y+oy)), BALL_SIZE//2)

        s1 = self.font_main.render(str(self.p1_score), True, NEON_BLUE)
        s2 = self.font_main.render(str(self.p2_score), True, NEON_PINK)
        self.screen.blit(s1, (WIDTH//4  + ox - s1.get_width()//2, 30+oy))
        self.screen.blit(s2, (3*WIDTH//4+ox - s2.get_width()//2, 30+oy))

        # Difficulty badge
        dc  = {"Easy": NEON_GREEN, "Medium": NEON_YELLOW, "Hard": NEON_PINK}[self.difficulty]
        dbl = self.font_tiny.render(self.difficulty, True, dc)
        self.screen.blit(dbl, (WIDTH//2 - dbl.get_width()//2, 8))

    def draw_game(self):
        ox = random.uniform(-self.shake_intensity, self.shake_intensity)
        oy = random.uniform(-self.shake_intensity, self.shake_intensity)
        self._draw_game_scene(ox, oy)

        if self.paused:
            self._draw_pause_overlay()
        else:
            hint = self.font_tiny.render("ESC — Pause", True, (80,80,100))
            self.screen.blit(hint, (WIDTH-115, 8))

        self.draw_vignette()

    def _draw_pause_overlay(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,170))
        self.screen.blit(overlay, (0,0))

        box = pygame.Rect(WIDTH//2-200, HEIGHT//2-150, 400, 300)
        pygame.draw.rect(self.screen, (25,28,55), box, border_radius=20)
        pygame.draw.rect(self.screen, NEON_BLUE,  box, 3, border_radius=20)

        title = self.font_main.render("PAUSED", True, NEON_BLUE)
        self.screen.blit(title, (WIDTH//2-title.get_width()//2, box.y+28))

        mouse = pygame.mouse.get_pos()
        opts  = [("RESUME",    "ESC / P", NEON_GREEN),
                 ("LEAVE GAME","L",        NEON_PINK)]
        self._pause_rects = {}
        for i,(label,key,col) in enumerate(opts):
            r = pygame.Rect(box.x+30, box.y+120+i*70, box.width-60, 50)
            self._pause_rects[label] = r
            hover = r.collidepoint(mouse)
            draw_button(self.screen, r, label, self.font_small, hover, col)
            ks = self.font_tiny.render(f"[ {key} ]", True, (130,130,150))
            self.screen.blit(ks, (r.right-ks.get_width()-12, r.centery-ks.get_height()//2))

    # ── END SCREEN ────────────────────────────────────────────────────

    def _emoji(self, glyph, size=28):
        """
        Render a single emoji using the best available colour-emoji font on
        the system, falling back gracefully to a plain white question mark so
        the layout never breaks on systems without emoji fonts installed.
        Rendered surfaces are cached by (glyph, size) to avoid per-frame work.
        """
        key = ("emoji", glyph, size)
        if key in getattr(self, "_emoji_cache", {}):
            return self._emoji_cache[key]
        if not hasattr(self, "_emoji_cache"):
            self._emoji_cache = {}

        # Candidate font names in priority order (macOS, Windows, Linux)
        candidates = [
            "Apple Color Emoji",
            "Segoe UI Emoji",
            "Noto Color Emoji",
            "Noto Emoji",
            "EmojiOne",
            "Twemoji Mozilla",
            "Symbola",
        ]
        surf = None
        for name in candidates:
            try:
                f = pygame.font.SysFont(name, size)
                s = f.render(glyph, True, WHITE)
                # A successful emoji render is noticeably wider than a fallback box
                if s.get_width() > size // 2:
                    surf = s
                    break
            except Exception:
                continue

        if surf is None:
            # Hard fallback: render the raw character with the default UI font
            surf = self.font_ui.render(glyph, True, WHITE)

        self._emoji_cache[key] = surf
        return surf

    def _draw_stat_card(self, rect, emoji, label, value, accent_col):
        """Draw a single rounded stat card with emoji, label and value."""
        # Card background + border
        pygame.draw.rect(self.screen, (22, 26, 54), rect, border_radius=14)
        pygame.draw.rect(self.screen, accent_col,   rect, 2,  border_radius=14)

        # Thin colour bar along the top edge
        bar = pygame.Rect(rect.x + 10, rect.y, rect.width - 20, 3)
        pygame.draw.rect(self.screen, accent_col, bar, border_radius=2)

        # Emoji
        em   = self._emoji(emoji, 26)
        ex   = rect.centerx - em.get_width() // 2
        ey   = rect.y + 14
        self.screen.blit(em, (ex, ey))

        # Value  (large, bright)
        v_surf = self.font_medium.render(str(value), True, WHITE)
        self.screen.blit(v_surf, (rect.centerx - v_surf.get_width()//2,
                                   rect.y + 46))

        # Label  (small, dim)
        l_surf = self.font_tiny.render(label, True, GREY)
        self.screen.blit(l_surf, (rect.centerx - l_surf.get_width()//2,
                                   rect.y + 84))

    def draw_end(self):
        self.draw_background()

        # ── Save stats once ───────────────────────────────────────────
        if not self.stats_saved:
            if self.username:
                self.api.update_profile(self.username, win=self.end_player_won)
                self.profile = self.api.create_or_load_profile(self.username)
                self.leaderboard.record(self.username, self.end_player_won)
            self.stats_saved = True

        won = self.end_player_won
        col = NEON_GREEN if won else NEON_PINK

        # ── Animated winner banner ────────────────────────────────────
        pulse = 1.0 + 0.045 * math.sin(time.time() * 4.5)
        trophy_em = self._emoji("🏆" if won else "🤖", 38)
        banner_txt = self.font_main.render(
            f"  {'YOU WIN!' if won else 'CPU WINS!'}", True, col)

        # Glow halo behind banner
        glow = pygame.Surface((banner_txt.get_width() + 100, 70), pygame.SRCALPHA)
        for r in range(35, 0, -4):
            a = int(60 * (r / 35))
            pygame.draw.ellipse(glow, (*col, a),
                (35 - r, 35 - r//2, banner_txt.get_width() + r*2, r))
        self.screen.blit(glow, (WIDTH//2 - glow.get_width()//2, 28))

        # Scale-pulse the banner
        bw = int(banner_txt.get_width() * pulse)
        bh = int(banner_txt.get_height() * pulse)
        banner_scaled = pygame.transform.smoothscale(banner_txt, (max(1, bw), max(1, bh)))
        bx = WIDTH//2 - (trophy_em.get_width() + banner_scaled.get_width()) // 2
        by = 30
        self.screen.blit(trophy_em,    (bx, by + banner_scaled.get_height()//2 - trophy_em.get_height()//2))
        self.screen.blit(banner_scaled,(bx + trophy_em.get_width(), by))

        # ── Score pill ────────────────────────────────────────────────
        score_str  = f"{self.p1_score}   —   {self.p2_score}"
        score_surf = self.font_medium.render(score_str, True, WHITE)
        pill = pygame.Rect(WIDTH//2 - score_surf.get_width()//2 - 20,
                           96, score_surf.get_width() + 40, 38)
        pygame.draw.rect(self.screen, (35, 38, 72), pill, border_radius=20)
        pygame.draw.rect(self.screen, (70, 74, 110), pill, 1, border_radius=20)

        # Colour the two score numbers individually
        you_s  = self.font_medium.render(str(self.p1_score), True, NEON_BLUE)
        sep_s  = self.font_medium.render("   —   ",           True, (80,80,100))
        cpu_s  = self.font_medium.render(str(self.p2_score), True, NEON_PINK)
        row_w  = you_s.get_width() + sep_s.get_width() + cpu_s.get_width()
        rx     = WIDTH//2 - row_w//2
        ry     = pill.y + (pill.height - you_s.get_height())//2
        self.screen.blit(you_s, (rx, ry))
        self.screen.blit(sep_s, (rx + you_s.get_width(), ry))
        self.screen.blit(cpu_s, (rx + you_s.get_width() + sep_s.get_width(), ry))

        # ── Stat cards (2 × 2 grid) ───────────────────────────────────
        matches   = self.p1_score + self.p2_score
        avg_rally = round(self.stats["total_hits"] / matches, 1) if matches else 0.0
        dur       = self.stats["duration"]
        dur_str   = f"{dur//60}m {dur%60:02d}s" if dur >= 60 else f"{dur}s"

        # Performance badge: comment on the match quality
        if self.stats["max_rally"] >= 10:
            badge_emoji, badge_text = "🔥", "EPIC RALLY!"
        elif self.stats["total_hits"] >= 30:
            badge_emoji, badge_text = "⚡", "HIGH INTENSITY"
        elif won and self.p2_score == 0:
            badge_emoji, badge_text = "👑", "PERFECT GAME"
        elif won:
            badge_emoji, badge_text = "🎯", "WELL PLAYED"
        else:
            badge_emoji, badge_text = "💪", "BETTER LUCK NEXT TIME"

        cards = [
            ("⏱", "DURATION",      dur_str,          NEON_BLUE),
            ("🏓", "LONGEST RALLY", str(self.stats["max_rally"]), NEON_YELLOW),
            ("💥", "TOTAL HITS",    str(self.stats["total_hits"]), NEON_PINK),
            ("📊", "AVG RALLY",     str(avg_rally),   NEON_PURPLE),
        ]

        card_w, card_h = 190, 112
        gap            = 14
        grid_w         = card_w * 2 + gap
        gx             = WIDTH//2 - grid_w//2
        gy             = 148

        for i, (em, lbl, val, accent) in enumerate(cards):
            cx = gx + (i % 2) * (card_w + gap)
            cy = gy + (i // 2) * (card_h + gap)
            self._draw_stat_card(pygame.Rect(cx, cy, card_w, card_h),
                                 em, lbl, val, accent)

        # ── Performance badge ─────────────────────────────────────────
        badge_y   = gy + card_h * 2 + gap * 2 + 2
        badge_em  = self._emoji(badge_emoji, 22)
        badge_lbl = self.font_ui.render(badge_text, True, NEON_YELLOW)
        badge_w   = badge_em.get_width() + 8 + badge_lbl.get_width() + 28
        badge_r   = pygame.Rect(WIDTH//2 - badge_w//2, badge_y, badge_w, 32)
        pygame.draw.rect(self.screen, (45, 42, 18), badge_r, border_radius=16)
        pygame.draw.rect(self.screen, NEON_YELLOW,  badge_r, 1, border_radius=16)
        self.screen.blit(badge_em,  (badge_r.x + 10, badge_r.y + 5))
        self.screen.blit(badge_lbl, (badge_r.x + 10 + badge_em.get_width() + 8,
                                      badge_r.y + (badge_r.height - badge_lbl.get_height())//2))

        # ── Profile summary strip ─────────────────────────────────────
        if self.profile:
            total_m  = self.profile.get("total_matches", 1)
            wr       = round(self.profile.get("total_wins", 0) / max(1, total_m) * 100)
            lv       = self.profile.get("level", 1)
            pw       = self.profile.get("total_wins", 0)

            strip_y  = badge_y + 40
            strip    = pygame.Rect(gx, strip_y, grid_w, 34)
            pygame.draw.rect(self.screen, (20, 22, 48), strip, border_radius=10)
            pygame.draw.rect(self.screen, (50, 52, 80), strip, 1, border_radius=10)

            pf_em  = self._emoji("🧑‍💻", 18)
            pf_txt = self.font_tiny.render(
                f"  {self.username}   Lv.{lv}   {pw} wins   {wr}% win rate",
                True, (190, 190, 210))
            row_surf_w = pf_em.get_width() + pf_txt.get_width()
            px = strip.centerx - row_surf_w // 2
            py = strip.y + (strip.height - pf_txt.get_height()) // 2
            self.screen.blit(pf_em,  (px, py - 1))
            self.screen.blit(pf_txt, (px + pf_em.get_width(), py))

        # ── Action buttons ────────────────────────────────────────────
        mouse   = pygame.mouse.get_pos()
        btn_y   = HEIGHT - 62
        btn_gap = 16
        btn_w   = 210

        again_rect = pygame.Rect(WIDTH//2 - btn_w - btn_gap//2, btn_y, btn_w, 48)
        menu_rect  = pygame.Rect(WIDTH//2 + btn_gap//2,          btn_y, btn_w, 48)

        draw_button(self.screen, again_rect, "▶  PLAY AGAIN",
                    self.font_small, again_rect.collidepoint(mouse), NEON_GREEN)
        draw_button(self.screen, menu_rect,  "⌂  MAIN MENU",
                    self.font_small, menu_rect.collidepoint(mouse), NEON_BLUE)

        hint = self.font_tiny.render("R — rematch   M — menu", True, (70, 72, 95))
        self.screen.blit(hint, (WIDTH//2 - hint.get_width()//2, HEIGHT - 18))

        self._end_again_rect = again_rect
        self._end_menu_rect  = menu_rect

        self.draw_vignette()

    # ── LEADERBOARD SCREEN ────────────────────────────────────────────

    def draw_leaderboard(self):
        self.draw_background()

        title = self.font_medium.render("🏆  LEADERBOARD", True, NEON_ORANGE)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 40))

        entries = self.leaderboard.top()
        if not entries:
            msg = self.font_small.render("No games recorded yet.", True, GREY)
            self.screen.blit(msg, (WIDTH//2 - msg.get_width()//2, HEIGHT//2 - 20))
        else:
            headers = ["#", "Name", "Wins", "Losses", "Win %"]
            cols    = [80, 220, 460, 590, 720]
            hy      = 106
            for i, (h, cx) in enumerate(zip(headers, cols)):
                hs = self.font_ui.render(h, True, GREY)
                self.screen.blit(hs, (cx, hy))

            pygame.draw.line(self.screen, (60,60,80),
                (60, hy+24), (WIDTH-60, hy+24), 1)

            for rank, entry in enumerate(entries, 1):
                ry    = hy + 36 + (rank-1)*38
                total = entry["wins"] + entry["losses"]
                rate  = f"{round(entry['wins']/total*100)}%" if total else "—"
                cells = [str(rank), entry["name"],
                         str(entry["wins"]), str(entry["losses"]), rate]
                is_me = (entry["name"] == self.username)
                row_col = NEON_GREEN if is_me else WHITE
                for cell, cx in zip(cells, cols):
                    cs = self.font_small.render(cell, True, row_col)
                    self.screen.blit(cs, (cx, ry))

        mouse = pygame.mouse.get_pos()
        back  = pygame.Rect(WIDTH//2-90, HEIGHT-70, 180, 46)
        draw_button(self.screen, back, "◀  BACK", self.font_small,
                    back.collidepoint(mouse), NEON_BLUE)
        self._lb_back_rect = back
        self.draw_vignette()

    # ── QUIT CONFIRMATION OVERLAY ─────────────────────────────────────

    def draw_quit_confirm(self):
        """Modal overlay asking the user to confirm quitting."""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        box = pygame.Rect(WIDTH//2 - 220, HEIGHT//2 - 110, 440, 220)
        pygame.draw.rect(self.screen, (30, 28, 55), box, border_radius=18)
        pygame.draw.rect(self.screen, NEON_ORANGE,  box, 3,  border_radius=18)

        title = self.font_medium.render("Quit PONG PRO?", True, NEON_ORANGE)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, box.y + 26))

        sub = self.font_tiny.render("Your progress will be saved.", True, GREY)
        self.screen.blit(sub, (WIDTH//2 - sub.get_width()//2, box.y + 72))

        mouse = pygame.mouse.get_pos()
        gap   = 20
        bw    = 160
        total = bw * 2 + gap
        bx    = WIDTH//2 - total//2
        by    = box.y + 128

        yes_rect = pygame.Rect(bx,        by, bw, 48)
        no_rect  = pygame.Rect(bx+bw+gap, by, bw, 48)
        draw_button(self.screen, yes_rect, "QUIT  ✕",
                    self.font_small, yes_rect.collidepoint(mouse), NEON_PINK)
        draw_button(self.screen, no_rect,  "CANCEL",
                    self.font_small, no_rect.collidepoint(mouse),  NEON_GREEN)
        self._qc_yes_rect = yes_rect
        self._qc_no_rect  = no_rect

    # ── CONTROLS SCREEN ───────────────────────────────────────────────

    def draw_controls(self):
        self.draw_background()

        title = self.font_medium.render("⌨  CONTROLS", True, NEON_PURPLE)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 40))

        sub = self.font_tiny.render(
            "Click a binding and press any key to remap", True, GREY)
        self.screen.blit(sub, (WIDTH//2 - sub.get_width()//2, 90))

        mouse    = pygame.mouse.get_pos()
        actions  = [("up",    "Move Up"),
                    ("down",  "Move Down"),
                    ("pause", "Pause")]
        box_w    = 500
        bx       = WIDTH//2 - box_w//2
        self._ctrl_rects = {}

        for i, (key_name, label) in enumerate(actions):
            ry   = 140 + i * 72
            row  = pygame.Rect(bx, ry, box_w, 54)
            pygame.draw.rect(self.screen, (22,24,50), row, border_radius=10)
            pygame.draw.rect(self.screen, (50,52,80), row, 1, border_radius=10)

            lbl  = self.font_small.render(label, True, WHITE)
            self.screen.blit(lbl, (row.x+20, row.centery - lbl.get_height()//2))

            current_key  = self.bindings.get(key_name, DEFAULT_BINDINGS[key_name])
            key_str      = pygame.key.name(current_key).upper()
            is_remapping = (self.remap_target == key_name)
            btn_r        = pygame.Rect(row.right - 170, row.y + 7, 160, 40)
            hover        = btn_r.collidepoint(mouse)
            btn_col      = NEON_YELLOW if is_remapping else NEON_PURPLE

            if is_remapping:
                # Two-line "waiting" state — always fits
                pygame.draw.rect(self.screen, (60, 50, 10), btn_r, border_radius=10)
                pygame.draw.rect(self.screen, NEON_YELLOW,  btn_r, 2, border_radius=10)
                l1 = self.font_tiny.render("PRESS KEY", True, NEON_YELLOW)
                l2 = self.font_tiny.render("ESC to cancel", True, (160, 140, 60))
                self.screen.blit(l1, (btn_r.centerx - l1.get_width()//2, btn_r.y + 5))
                self.screen.blit(l2, (btn_r.centerx - l2.get_width()//2, btn_r.y + 22))
            else:
                draw_button(self.screen, btn_r, key_str, self.font_ui, hover, btn_col)
            self._ctrl_rects[key_name] = btn_r

        # Reset defaults
        reset_rect = pygame.Rect(WIDTH//2-90, 380, 180, 44)
        draw_button(self.screen, reset_rect, "RESET DEFAULTS",
                    self.font_tiny,
                    reset_rect.collidepoint(mouse), GREY)
        self._ctrl_reset_rect = reset_rect

        # Sounds toggle
        sound_rect = pygame.Rect(WIDTH//2-90, 438, 180, 44)
        sound_lbl  = f"SOUND: {'ON' if self.sounds.enabled else 'OFF'}"
        sound_col  = NEON_GREEN if self.sounds.enabled else NEON_PINK
        draw_button(self.screen, sound_rect, sound_lbl,
                    self.font_tiny, sound_rect.collidepoint(mouse), sound_col)
        self._sound_toggle_rect = sound_rect

        # Back
        back = pygame.Rect(WIDTH//2-90, HEIGHT-70, 180, 46)
        draw_button(self.screen, back, "◀  BACK",
                    self.font_small, back.collidepoint(mouse), NEON_BLUE)
        self._ctrl_back_rect = back

        self.draw_vignette()

    # ══════════════════════════════════════════════════════════════════
    #  EVENT HANDLING PER STATE
    # ══════════════════════════════════════════════════════════════════

    def _handle_splash(self, event):
        # Skip on click or any key
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.state = "LOGIN"

    def _handle_login(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._try_login()
            elif event.key == pygame.K_BACKSPACE:
                self.temp_username = self.temp_username[:-1]
                self.login_error   = ""
            elif event.key == pygame.K_ESCAPE:
                # Go back to splash rather than hard-quitting
                self.state = "SPLASH"
                self.splash_timer = 0.0
            elif len(self.temp_username) < 18 and event.unicode.isprintable():
                self.temp_username += event.unicode
                self.login_error    = ""
        elif event.type == pygame.MOUSEBUTTONDOWN:
            btn = pygame.Rect(WIDTH//2-100, HEIGHT//2+60, 200, 48)
            if btn.collidepoint(event.pos):
                self._try_login()

    def _try_login(self):
        name = self.temp_username.strip()
        if len(name) < 2:
            self.login_error = "Name must be at least 2 characters."
            return
        self.username = name
        self.profile  = self.api.create_or_load_profile(name)
        self._save_prefs()
        self.state = "MENU"

    def _handle_menu(self, event):
        # If quit confirm overlay is active, handle it exclusively
        if self.quit_confirm:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_n:
                    self.quit_confirm = False
                elif event.key == pygame.K_RETURN or event.key == pygame.K_y:
                    pygame.quit(); sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if hasattr(self, "_qc_yes_rect") and self._qc_yes_rect.collidepoint(event.pos):
                    pygame.quit(); sys.exit()
                if hasattr(self, "_qc_no_rect") and self._qc_no_rect.collidepoint(event.pos):
                    self.quit_confirm = False
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.quit_confirm = True
            return
        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            for d, r in self._diff_rects.items():
                if r.collidepoint(pos):
                    self.difficulty = d
                    self._save_prefs()
                    return
            if self._play_rect.collidepoint(pos):
                self.reset_game_objects()
                self.countdown_start = time.time()
                self.countdown_last  = -1
                self.state = "COUNTDOWN"
                return
            if self._lb_rect.collidepoint(pos):
                self.state = "LEADERBOARD"
                return
            if self._ct_rect.collidepoint(pos):
                self.remap_target = None
                self.state = "CONTROLS"

    def _handle_countdown(self, event):
        pass   # countdown advances automatically in draw_countdown()

    def _handle_game(self, event):
        if event.type == pygame.KEYDOWN:
            pause_key = self.bindings.get("pause", DEFAULT_BINDINGS["pause"])
            if event.key == pause_key or event.key == pygame.K_p:
                self.paused = not self.paused
            elif self.paused:
                if event.key == pygame.K_l:
                    self.state  = "MENU"
                    self.paused = False
        elif event.type == pygame.MOUSEBUTTONDOWN and self.paused:
            pos = event.pos
            if hasattr(self, "_pause_rects"):
                if self._pause_rects.get("RESUME", pygame.Rect(0,0,0,0)).collidepoint(pos):
                    self.paused = False
                elif self._pause_rects.get("LEAVE GAME", pygame.Rect(0,0,0,0)).collidepoint(pos):
                    self.state  = "MENU"
                    self.paused = False

    def _handle_end(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            if hasattr(self, "_end_again_rect") and self._end_again_rect.collidepoint(pos):
                self.reset_game_objects()
                self.countdown_start = time.time()
                self.countdown_last  = -1
                self.state = "COUNTDOWN"
            elif hasattr(self, "_end_menu_rect") and self._end_menu_rect.collidepoint(pos):
                self.state = "MENU"
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.reset_game_objects()
                self.countdown_start = time.time()
                self.countdown_last  = -1
                self.state = "COUNTDOWN"
            elif event.key == pygame.K_m:
                self.state = "MENU"

    def _handle_leaderboard(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if hasattr(self, "_lb_back_rect") and \
               self._lb_back_rect.collidepoint(event.pos):
                self.state = "MENU"
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.state = "MENU"

    def _handle_controls(self, event):
        if event.type == pygame.KEYDOWN:
            if self.remap_target:
                # Capture new key
                if event.key != pygame.K_ESCAPE:
                    self.bindings[self.remap_target] = event.key
                    self._save_prefs()
                self.remap_target = None
                return
            if event.key == pygame.K_ESCAPE:
                self.state = "MENU"
        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            # Key remap buttons
            if hasattr(self, "_ctrl_rects"):
                for key_name, r in self._ctrl_rects.items():
                    if r.collidepoint(pos):
                        self.remap_target = key_name
                        return
            if hasattr(self, "_ctrl_reset_rect") and \
               self._ctrl_reset_rect.collidepoint(pos):
                self.bindings = dict(DEFAULT_BINDINGS)
                self._save_prefs()
                return
            if hasattr(self, "_sound_toggle_rect") and \
               self._sound_toggle_rect.collidepoint(pos):
                self.sounds.enabled = not self.sounds.enabled
                return
            if hasattr(self, "_ctrl_back_rect") and \
               self._ctrl_back_rect.collidepoint(pos):
                self.state = "MENU"

    # ══════════════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════════════════

    def run(self):
        handler_map = {
            "SPLASH":      self._handle_splash,
            "LOGIN":       self._handle_login,
            "MENU":        self._handle_menu,
            "COUNTDOWN":   self._handle_countdown,
            "GAME":        self._handle_game,
            "END":         self._handle_end,
            "LEADERBOARD": self._handle_leaderboard,
            "CONTROLS":    self._handle_controls,
        }

        while True:
            dt = self.clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                handler = handler_map.get(self.state)
                if handler:
                    handler(event)

            # ── Update ─────────────────────────────────────────────
            if self.state == "SPLASH":
                self.splash_timer += dt
                if self.splash_timer >= self.splash_duration:
                    self.state = "LOGIN"

            elif self.state == "GAME" and not self.paused:
                up_key   = self.bindings.get("up",   DEFAULT_BINDINGS["up"])
                down_key = self.bindings.get("down", DEFAULT_BINDINGS["down"])
                keys = pygame.key.get_pressed()
                if keys[up_key]   and self.p1_y > 0:
                    self.p1_y -= 8
                if keys[down_key] and self.p1_y < HEIGHT - PADDLE_HEIGHT:
                    self.p1_y += 8
                self.handle_ai()
                self.update_physics()

            # ── Draw ───────────────────────────────────────────────
            draw_map = {
                "SPLASH":      self.draw_splash,
                "LOGIN":       self.draw_login,
                "MENU":        self.draw_menu,
                "COUNTDOWN":   self.draw_countdown,
                "GAME":        self.draw_game,
                "END":         self.draw_end,
                "LEADERBOARD": self.draw_leaderboard,
                "CONTROLS":    self.draw_controls,
            }
            draw_fn = draw_map.get(self.state)
            if draw_fn:
                draw_fn()

            pygame.display.flip()


# ══════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    PongPro().run()
