from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, json, sys, os

router = APIRouter()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

_adsb_lock = asyncio.Lock()


@router.websocket("/ws/adsb")
async def ws_adsb(websocket: WebSocket):
    await websocket.accept()

    if _adsb_lock.locked():
        await websocket.send_json({"type": "error", "message": "ADS-B capture already in progress"})
        await websocket.close()
        return

    try:
        raw = await websocket.receive_text()
        params = json.loads(raw)
        duration = float(params.get("duration", 30))
    except Exception:
        await websocket.send_json({"type": "error", "message": "Invalid params"})
        await websocket.close()
        return

    async with _adsb_lock:
        try:
            import config
            from protocols.adsb import capture_iq, compute_envelope, decode_iq

            adsb_config = config.PROTOCOLS["adsb"]

            await websocket.send_json({"type": "status", "phase": "capturing", "duration": duration})

            iq_data = await asyncio.to_thread(
                capture_iq, adsb_config, duration, config.RX_SERIAL
            )

            if iq_data is None or len(iq_data) < 1000:
                await websocket.send_json({"type": "error", "message": "Capture failed or too short"})
                return

            await websocket.send_json({"type": "status", "phase": "decoding"})

            result_box = {}

            def on_aircraft(aircraft_dict, msg_count):
                result_box["aircraft"] = aircraft_dict
                result_box["msg_count"] = msg_count

            envelope = await asyncio.to_thread(compute_envelope, iq_data)
            await asyncio.to_thread(decode_iq, envelope, adsb_config["sample_rate"], on_aircraft)

            aircraft_raw = result_box.get("aircraft", {})
            msg_count = result_box.get("msg_count", 0)

            aircraft_list = []
            for icao, ac in aircraft_raw.items():
                aircraft_list.append({
                    "icao":     icao,
                    "callsign": ac.get("callsign"),
                    "alt":      ac.get("alt"),
                    "lat":      ac.get("lat"),
                    "lon":      ac.get("lon"),
                    "speed":    round(ac["speed"], 1) if ac.get("speed") is not None else None,
                    "heading":  round(ac["heading"], 1) if ac.get("heading") is not None else None,
                })

            await websocket.send_json({
                "type":           "done",
                "aircraft":       aircraft_list,
                "aircraft_count": len(aircraft_list),
                "msg_count":      msg_count,
                "with_position":  sum(1 for a in aircraft_list if a["lat"] is not None),
            })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass
