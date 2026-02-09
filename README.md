# Starlink NMEA Bridge

Serve Starlink dish location as NMEA 0183 sentences for OpenCPN (or any NMEA client).

## Features

- Emits `GPRMC` + `GPGGA` every second
- TCP server mode (OpenCPN compatible)
- UDP output mode (optional broadcast)

## Requirements

- Python 3.9+
- Starlink dish reachable on your LAN
- Python dependency: `starlink-grpc-tools`

## Install

```
pip install starlink-grpc-tools
```

## Run

TCP server (recommended for OpenCPN):

```
python3 starlink_nmea.py --mode tcp --host 0.0.0.0 --port 10110 --verbose
```

UDP output (to local OpenCPN or other consumer):

```
python3 starlink_nmea.py --mode udp --host 127.0.0.1 --port 10110 --verbose
```

Dish auto-detection is enabled by default. To force a specific dish IP:

```
python3 starlink_nmea.py --mode tcp --dish-host 192.168.100.1
```

Or via environment variable:

```
export STARLINK_DISH_IP=192.168.100.1
```

UDP broadcast (for LAN listeners):

```
python3 starlink_nmea.py --mode udp --broadcast --host 255.255.255.255 --port 10110
```

## OpenCPN Setup

1) Add a connection:
   - Type: `Network`
   - Protocol: `TCP` (or `UDP`)
   - Address: `127.0.0.1` (or the server host)
   - Port: `10110` (or your chosen port)

2) Enable the connection.

## Run at Startup (macOS launchd)

1) Update the script path in `launchd/com.keeldragger.starlink-nmea.plist` if needed.

2) Install and load:

```
cp launchd/com.keeldragger.starlink-nmea.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.keeldragger.starlink-nmea.plist
```

3) Stop/unload:

```
launchctl unload ~/Library/LaunchAgents/com.keeldragger.starlink-nmea.plist
```

## Run at Startup (Linux systemd)

1) Copy the service file and update paths if needed:

```
sudo mkdir -p /opt/starlink-nmea
sudo cp -r . /opt/starlink-nmea
sudo cp systemd/starlink-nmea.service /etc/systemd/system/
```

2) Enable and start:

```
sudo systemctl daemon-reload
sudo systemctl enable --now starlink-nmea.service
```

3) View logs:

```
journalctl -u starlink-nmea.service -f
```

## Starlink Notes

No special Starlink configuration is usually required.

- Your computer must reach the dish management IP, typically `192.168.100.1`.
- If using a third-party router in bypass mode, add a static route to `192.168.100.1`.
- Ensure local firewall rules allow access to the dish API.

## Troubleshooting

- **No position data**: Confirm the dish is reachable and `starlink-grpc-tools` is installed.
- **OpenCPN shows no GPS**: Check IP/port match and firewall rules.
- **Multiple clients**: Use TCP mode; it supports multiple connections.
