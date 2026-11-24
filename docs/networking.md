# The drone's Wi-Fi and your internet

This is the fundamental challenge. The Tello drone creates its own WiFi access point (`TELLO-XXXXXX` at `192.168.10.1`), and when your machine connects to it, you lose internet access. This is a dealbreaker for production use — you can't reach MCP servers, cloud APIs, or anything else online.

There are a few ways to solve this, each with different trade-offs.

**Option 1: Dual Network Interfaces (simplest and most reliable)**

Use your machine's built-in WiFi to connect to the Tello, and plug in an Ethernet cable for internet. Most laptops and all desktops support this out of the box. Your OS routing table will send traffic to `192.168.10.x` over WiFi and everything else over Ethernet. This "just works" on Linux, macOS, and Windows without any special configuration — the OS prefers the wired interface for default gateway automatically.

**Option 2: USB WiFi Adapter (no Ethernet available)**

If you don't have Ethernet access, grab a cheap USB WiFi dongle. Connect the dongle to the Tello AP, and keep your built-in WiFi on your home/office network. You'd then configure the backend to bind specifically to the USB adapter's interface for Tello UDP traffic. This requires a small amount of OS-level network config but works well.

**Option 3: Dedicated Ground Station Device (best for production)**

Deploy a small dedicated device — a Raspberry Pi 4/5 or an Intel NUC mini PC — as your permanent "ground station." This device connects its WiFi to the Tello drone and its Ethernet to your local network (router). Your webapp runs on this device via Docker, and you access it from any browser on your regular network.

```
                        YOUR LOCAL NETWORK (with internet)
                        ┌──────────────────────────────────┐
                        │                                  │
  ┌──────────┐    WiFi  │   ┌──────────┐     Ethernet      │    ┌──────────┐
  │  Tello   │◄─────────┤   │  Ground  │◄─────────────────►├───►│  Router  │──► Internet
  │  Drone   │  AP mode  │   │  Station │    192.168.1.x    │    │          │
  │192.168.  │          │   │  (Pi/NUC)│                   │    └──────────┘
  │  10.1    │ UDP 8889 │   │          │                   │
  └──────────┘   8890   │   │ Docker:  │     :3000 (UI)    │    ┌──────────┐
               11111   │   │ backend  │◄────────────────────────│ Your     │
                        │   │ frontend │     :8000 (API)    │    │ Laptop/  │
                        │   └──────────┘                   │    │ Desktop  │
                        │                                  │    └──────────┘
                        └──────────────────────────────────┘
```

The beauty of this setup is that the ground station has two network paths simultaneously — WiFi to the drone, Ethernet to your LAN and internet. Your laptop just opens `http://groundstation.local:3000` in a browser. The backend on the ground station can reach both the Tello (via WiFi UDP) and the internet (via Ethernet) for MCP servers, AI APIs, etc.
