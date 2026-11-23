from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Drone connection
    tello_host: str = "192.168.10.1"
    tello_retry_count: int = 3

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Telemetry
    telemetry_poll_hz: float = 4.0

    # Flight log (SQLite): every telemetry frame and command, per connection
    flight_log_enabled: bool = True
    flight_log_path: str = "data/flights.db"

    # Video
    video_fps: int = 30
    video_jpeg_quality: int = 70

    # Mock mode (for development/testing without a physical drone)
    use_mock_drone: bool = False
    # Seconds each mock flight command "takes" (0 = instant; ~0.8 makes the
    # sequencer's live step highlighting visible in mock mode)
    mock_command_delay_s: float = 0.0
    # Starting battery and Wi-Fi signal for the mock drone (handy for trying
    # out the warnings, e.g. TELLO_MOCK_BATTERY_PCT=20 TELLO_MOCK_WIFI_SNR=30)
    mock_battery_pct: int = 85
    mock_wifi_snr: int = 90

    # Flight sequencer
    sequences_dir: str = "data/sequences"
    sequence_min_battery_pct: int = 30   # refuse to start a sequence below this
    sequence_flip_min_battery_pct: int = 50  # Tello refuses flips below ~50%
    sequence_abort_battery_pct: int = 15  # land mid-sequence if battery drops below this

    # On-screen flight alerts
    battery_low_pct: int = 30       # amber "land soon" banner at or below this
    battery_critical_pct: int = 15  # red "land now" banner + beep at or below this
    # Tello answers "wifi?" with a signal-to-noise figure (higher is better, ~90
    # right next to the drone). These are starting points: tune them to your space.
    wifi_snr_weak: int = 40         # amber "move closer" banner at or below this
    wifi_snr_critical: int = 20     # red banner, and sequences refuse to start
    wifi_poll_interval_s: float = 3.0  # how often to ask the drone for its signal

    # Camera: photos and clips saved on this machine
    media_dir: str = "data/media"
    record_fps: int = 30            # frames per second written to clips
    record_max_s: int = 300         # clips stop themselves after this many seconds
    camera_start_timeout_s: float = 8.0  # wait this long for the first video frame

    # Tello "go x y z" uses y = left; flip this if orbits/glides go sideways the wrong way
    go_y_is_left: bool = True

    # Stick flying (game controller / hold-to-fly keyboard)
    rc_speed_limit_pct: int = 100  # hard cap on stick speed, 10-100 (% of the Tello's max)
    rc_timeout_s: float = 0.5      # no stick update for this long -> stop and hover

    model_config = {"env_prefix": "TELLO_"}


settings = Settings()
