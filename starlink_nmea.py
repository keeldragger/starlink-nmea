#!/usr/bin/env python3
"""
Serve NMEA 0183 position sentences from Starlink.

Default output: TCP server on 0.0.0.0:10110 (OpenCPN-compatible).
Requires: pip install starlink-grpc-tools
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import socket
import time
from typing import Any, Dict, Optional, Tuple


def nmea_checksum(sentence_body: str) -> str:
    checksum = 0
    for ch in sentence_body:
        checksum ^= ord(ch)
    return f"{checksum:02X}"


def format_lat_lon(value: float, is_lat: bool) -> Tuple[str, str]:
    hemi = "N" if is_lat else "E"
    if value < 0:
        hemi = "S" if is_lat else "W"
    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60.0
    if is_lat:
        return f"{degrees:02d}{minutes:06.3f}", hemi
    return f"{degrees:03d}{minutes:06.3f}", hemi


def build_rmc(
    ts_utc: dt.datetime,
    lat: float,
    lon: float,
    speed_knots: Optional[float] = None,
    track_deg: Optional[float] = None,
) -> str:
    time_str = ts_utc.strftime("%H%M%S")
    date_str = ts_utc.strftime("%d%m%y")
    lat_str, lat_hemi = format_lat_lon(lat, True)
    lon_str, lon_hemi = format_lat_lon(lon, False)
    speed = f"{(speed_knots or 0.0):.1f}"
    track = f"{(track_deg or 0.0):.1f}"
    body = f"GPRMC,{time_str}.00,A,{lat_str},{lat_hemi},{lon_str},{lon_hemi},{speed},{track},{date_str},,,A"
    return f"${body}*{nmea_checksum(body)}"


def build_gga(
    ts_utc: dt.datetime,
    lat: float,
    lon: float,
    alt_m: Optional[float] = None,
) -> str:
    time_str = ts_utc.strftime("%H%M%S")
    lat_str, lat_hemi = format_lat_lon(lat, True)
    lon_str, lon_hemi = format_lat_lon(lon, False)
    altitude = f"{(alt_m or 0.0):.1f}"
    body = f"GPGGA,{time_str}.00,{lat_str},{lat_hemi},{lon_str},{lon_hemi},1,08,1.0,{altitude},M,0.0,M,,"
    return f"${body}*{nmea_checksum(body)}"


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_attr(obj: Any, *names: str) -> Optional[Any]:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj.get(name)
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _extract_location(payload: Any) -> Optional[Dict[str, float]]:
    if payload is None:
        return None

    # Direct fields
    lat = _to_float(_get_attr(payload, "lat", "latitude"))
    lon = _to_float(_get_attr(payload, "lon", "longitude"))
    alt = _to_float(_get_attr(payload, "alt", "altitude", "altitude_m"))

    if lat is not None and lon is not None:
        return {"lat": lat, "lon": lon, "alt": alt or 0.0}

    # Nested gps_stats or location
    gps_stats = _get_attr(payload, "gps_stats", "gpsStats")
    if gps_stats:
        lat = _to_float(_get_attr(gps_stats, "lat", "latitude"))
        lon = _to_float(_get_attr(gps_stats, "lon", "longitude"))
        alt = _to_float(_get_attr(gps_stats, "alt", "altitude", "altitude_m"))
        if lat is not None and lon is not None:
            return {"lat": lat, "lon": lon, "alt": alt or 0.0}

    location = _get_attr(payload, "location", "position")
    if location:
        lat = _to_float(_get_attr(location, "lat", "latitude"))
        lon = _to_float(_get_attr(location, "lon", "longitude"))
        alt = _to_float(_get_attr(location, "alt", "altitude", "altitude_m"))
        if lat is not None and lon is not None:
            return {"lat": lat, "lon": lon, "alt": alt or 0.0}

    return None


def _probe_port(host: str, port: int, timeout_s: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def detect_dish_host(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit

    env_host = os.environ.get("STARLINK_DISH_IP") or os.environ.get("STARLINK_DISH_HOST")
    if env_host:
        return env_host

    for hostname in ("dish", "starlink"):
        try:
            ip = socket.gethostbyname(hostname)
            if ip:
                return ip
        except socket.gaierror:
            pass

    default_ip = "192.168.100.1"
    if _probe_port(default_ip, 9200, 0.5):
        return default_ip

    return None


def _call_with_host(func: Any, dish_host: Optional[str]) -> Any:
    if dish_host:
        try:
            return func(host=dish_host)
        except TypeError:
            try:
                return func(dish_host)
            except TypeError:
                return func()
    return func()


def get_starlink_location(dish_host: Optional[str]) -> Optional[Dict[str, float]]:
    try:
        import starlink_grpc  # type: ignore
    except Exception:
        return None

    # Try dish.get_location()
    try:
        dish = getattr(starlink_grpc, "dish", None)
        if dish and hasattr(dish, "get_location"):
            return _extract_location(_call_with_host(dish.get_location, dish_host))
    except Exception:
        pass

    # Try grpc.get_location()
    try:
        grpc_mod = getattr(starlink_grpc, "grpc", None)
        if grpc_mod and hasattr(grpc_mod, "get_location"):
            return _extract_location(_call_with_host(grpc_mod.get_location, dish_host))
    except Exception:
        pass

    # Try get_status()
    try:
        if hasattr(starlink_grpc, "get_status"):
            return _extract_location(_call_with_host(starlink_grpc.get_status, dish_host))
    except Exception:
        pass

    return None


def serve_tcp(
    bind_host: str,
    port: int,
    interval_s: float,
    dish_host: Optional[str],
    verbose: bool,
) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((bind_host, port))
    server.listen(5)
    server.setblocking(False)

    clients: list[socket.socket] = []
    if verbose:
        print(f"TCP server listening on {bind_host}:{port}")

    resolved_host = detect_dish_host(dish_host)
    last_detect = time.monotonic()

    while True:
        # Accept new clients
        while True:
            try:
                client, addr = server.accept()
                client.setblocking(False)
                clients.append(client)
                if verbose:
                    print(f"Client connected: {addr}")
            except BlockingIOError:
                break

        location = get_starlink_location(resolved_host)
        if location is None and time.monotonic() - last_detect > 30:
            resolved_host = detect_dish_host(dish_host)
            last_detect = time.monotonic()
        if location:
            ts = dt.datetime.utcnow()
            rmc = build_rmc(ts, location["lat"], location["lon"])
            gga = build_gga(ts, location["lat"], location["lon"], location.get("alt"))
            payload = f"{rmc}\r\n{gga}\r\n".encode("ascii")
            alive: list[socket.socket] = []
            for client in clients:
                try:
                    client.sendall(payload)
                    alive.append(client)
                except Exception:
                    try:
                        client.close()
                    except Exception:
                        pass
            clients = alive
            if verbose and not clients:
                print("No clients connected.")
        elif verbose:
            print("No Starlink location available.")

        time.sleep(interval_s)


def serve_udp(
    target_host: str,
    port: int,
    interval_s: float,
    dish_host: Optional[str],
    broadcast: bool,
    verbose: bool,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if broadcast:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if verbose:
        print(f"UDP output to {target_host}:{port} (broadcast={broadcast})")

    resolved_host = detect_dish_host(dish_host)
    last_detect = time.monotonic()

    while True:
        location = get_starlink_location(resolved_host)
        if location is None and time.monotonic() - last_detect > 30:
            resolved_host = detect_dish_host(dish_host)
            last_detect = time.monotonic()
        if location:
            ts = dt.datetime.utcnow()
            rmc = build_rmc(ts, location["lat"], location["lon"])
            gga = build_gga(ts, location["lat"], location["lon"], location.get("alt"))
            payload = f"{rmc}\r\n{gga}\r\n".encode("ascii")
            sock.sendto(payload, (target_host, port))
        elif verbose:
            print("No Starlink location available.")
        time.sleep(interval_s)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Starlink location as NMEA 0183.")
    parser.add_argument("--mode", choices=["tcp", "udp"], default="tcp", help="Output mode.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host for TCP or target for UDP.")
    parser.add_argument("--port", type=int, default=10110, help="Port for TCP/UDP.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between updates.")
    parser.add_argument(
        "--dish-host",
        default=None,
        help="Dish IP/host (auto-detected if omitted).",
    )
    parser.add_argument("--broadcast", action="store_true", help="Enable UDP broadcast.")
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "tcp":
        serve_tcp(args.host, args.port, args.interval, args.dish_host, args.verbose)
    else:
        serve_udp(args.host, args.port, args.interval, args.dish_host, args.broadcast, args.verbose)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
