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

    # Continuous (RC) control: hover if no stick input arrives within this window
    rc_timeout_ms: int = 500

    # Telemetry
    telemetry_poll_hz: float = 4.0

    # Flight log (SQLite): every telemetry frame and command, per connection
    flight_log_enabled: bool = True
    flight_log_path: str = "data/flights.db"

    # Vision (optional, needs requirements-vision.txt): detection overlay + tracking
    vision_enabled: bool = False
    vision_model: str = "yolov8n.pt"
    vision_confidence: float = 0.4
    vision_device: str = ""  # "" = auto, or "cpu", "cuda:0", ...
    vision_hz: float = 5.0
    # Tracking controller. Untuned defaults: start slow and adjust on a real drone.
    vision_track_max_speed: int = 30
    vision_track_gain_yaw: float = 60.0
    vision_track_gain_ud: float = 40.0
    vision_track_gain_fb: float = 40.0
    vision_track_target_height: float = 0.5

    # Video
    video_fps: int = 30
    video_jpeg_quality: int = 70

    # Mock mode (for development/testing without a physical drone)
    use_mock_drone: bool = False

    model_config = {"env_prefix": "TELLO_"}


settings = Settings()
