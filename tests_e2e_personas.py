"""tests_e2e_personas.py — Tests E2E avec 5 personas reels

Simule 5 utilisateurs differents avec des options variees.
Mesure le flux complet : preflight → soumission → routage → traitement.

Usage:
  source .venv/bin/activate
  PYTHONPATH=backend python3 tests_e2e_personas.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = os.getenv("ECONOMY_URL", "http://localhost:8001")

# ── URLs de test fiables ────────────────────────────────────────────────────
# Videos YouTube courtes (< 2 min → queue "short")
YT_SHORT = "https://www.youtube.com/watch?v=jNQXAC9IVRw"       # 0:19
YT_MEDIUM = "https://www.youtube.com/watch?v=9bZkp7q19f0s"      # 4:13 → queue "medium"
YT_LONG = "https://www.youtube.com/watch?v=RgKAFK5djSk"         # 3:28 → queue "medium"

# ── Output directory ────────────────────────────────────────────────────────
OUT = Path("/tmp/subvox-e2e")
OUT.mkdir(parents=True, exist_ok=True)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def log(event: str, **data):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **data}
    print(json.dumps(entry, default=str))
    sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════════════════
# PERSONAS
# ═══════════════════════════════════════════════════════════════════════════

PERSONAS = [
    {
        "name": "Alice",
        "description": "Utilisatrice freemium → traduit YouTube en FR, soft subs",
        "source_url": YT_SHORT,
        "target_lang": "fr",
        "mode": "translate",
        "pool": "community",
        "soft_subs": True,
        "expected_queue": "short",
        "wallet": "0xAliceFreemium" + uuid.uuid4().hex[:20],
    },
    {
        "name": "Bob",
        "description": "Premium → Twitter/X multi-langues ES + DE, hard subs",
        "source_url": YT_MEDIUM,
        "target_lang": "es",
        "mode": "translate",
        "pool": "personal",
        "soft_subs": False,
        "expected_queue": "medium",
        "wallet": "0xBobPremium" + uuid.uuid4().hex[:22],
    },
    {
        "name": "Charlie",
        "description": "Power user → download-only avec watermark removal (SUBTEST)",
        "source_url": YT_SHORT,
        "target_lang": "none",
        "mode": "download",
        "pool": "personal",
        "soft_subs": True,
        "expected_queue": "short",
        "wallet": "0xCharliePower" + uuid.uuid4().hex[:20],
    },
    {
        "name": "Diana",
        "description": "Visiteur anonyme → traduit en JA (visitor_token)",
        "source_url": YT_SHORT,
        "target_lang": "ja",
        "mode": "translate",
        "pool": "community",
        "soft_subs": True,
        "expected_queue": "short",
        "visitor_token": str(uuid.uuid4()),
    },
    {
        "name": "Eve",
        "description": "Multi-video X/Twitter → verifie group_id + jobs multiples",
        "source_url": YT_SHORT,
        "target_lang": "fr",
        "mode": "translate",
        "pool": "community",
        "soft_subs": True,
        "expected_queue": "short",
        "wallet": "0xEveMulti" + uuid.uuid4().hex[:22],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# ETAPE 1 — TEST PREFLIGHT
# ═══════════════════════════════════════════════════════════════════════════


async def test_preflight(client: httpx.AsyncClient, p: dict) -> dict:
    """Simule la validation du formulaire : estime duree + cout."""
    log("preflight_start", persona=p["name"])
    t0 = time.monotonic()

    resp = await client.post(
        f"{API}/jobs/preflight",
        json={
            "source_url": p["source_url"],
            "target_langs": [p["target_lang"]] if p["target_lang"] != "none" else [],
            "pool": p["pool"],
        },
        timeout=120,
    )

    elapsed = round(time.monotonic() - t0, 2)
    result = {
        "persona": p["name"],
        "status_code": resp.status_code,
        "elapsed_s": elapsed,
    }

    if resp.status_code == 200:
        data = resp.json()
        result.update({
            "success": True,
            "duration_s": data.get("duration_s"),
            "needs_auth": data.get("needs_auth", False),
            "platform_slug": data.get("platform_slug"),
            "cost": data.get("cost"),
            "has_enough": data.get("has_enough"),
            "pool_ok": data.get("pool_ok"),
        })
        log("preflight_ok",
            persona=p["name"],
            duration_s=data.get("duration_s"),
            cost=data.get("cost", {}).get("user_cost"),
            pool_ok=data.get("pool_ok"))
    else:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:200]
        result.update({"success": False, "error": str(detail)[:200]})
        log("preflight_error", persona=p["name"], status=resp.status_code, error=str(detail)[:100])

    return result


# ═══════════════════════════════════════════════════════════════════════════
# ETAPE 2 — TEST SOUMISSION
# ═══════════════════════════════════════════════════════════════════════════


async def test_submit(client: httpx.AsyncClient, p: dict) -> dict:
    """Soumet le job avec les options de la persona."""
    log("submit_start", persona=p["name"])

    payload = {
        "source_url": p["source_url"],
        "target_lang": p["target_lang"],
        "mode": p["mode"],
        "pool": p["pool"],
        "soft_subs": p.get("soft_subs", True),
    }
    if p.get("visitor_token"):
        payload["visitor_token"] = p["visitor_token"]

    t0 = time.monotonic()
    resp = await client.post(f"{API}/jobs/submit", json=payload, timeout=120)
    elapsed = round(time.monotonic() - t0, 2)

    result = {
        "persona": p["name"],
        "status_code": resp.status_code,
        "elapsed_s": elapsed,
    }

    if resp.status_code == 200:
        data = resp.json()
        result["success"] = True
        result["response"] = data

        # Verifier si multi-video
        if data.get("multi_video"):
            result["multi_video"] = True
            result["group_id"] = data.get("group_id")
            result["total_videos"] = data.get("total_videos")
            result["jobs"] = data.get("jobs", [])
            log("submit_multi", persona=p["name"],
                group_id=data.get("group_id", "")[:8],
                total=data.get("total_videos"),
                jobs=[j.get("job_id", "")[:8] for j in data.get("jobs", [])])
        else:
            result["job_id"] = data.get("job_id", "")
            result["queue_position"] = data.get("queue_position")
            result["cached"] = data.get("cached", False)
            result["video_index"] = data.get("video_index")
            result["source_job_id"] = data.get("source_job_id")
            result["discount_applicable"] = data.get("discount_applicable", False)
            result["group_id"] = data.get("group_id")
            log("submit_ok", persona=p["name"],
                job_id=data.get("job_id", "")[:8],
                queue=data.get("queue_position"),
                cached=data.get("cached", False))
    else:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:200]
        result.update({"success": False, "error": str(detail)[:200]})
        log("submit_error", persona=p["name"], status=resp.status_code, error=str(detail)[:100])

    return result


# ═══════════════════════════════════════════════════════════════════════════
# ETAPE 3 — TEST SOURCE-LANGUAGES
# ═══════════════════════════════════════════════════════════════════════════


async def test_source_languages(client: httpx.AsyncClient, p: dict) -> dict:
    """Verifie que l'endpoint source-languages retourne les bonnes langues."""
    log("source_languages_start", persona=p["name"])

    resp = await client.get(
        f"{API}/jobs/source-languages",
        params={"source_url": p["source_url"]},
        timeout=10,
    )

    result = {
        "persona": p["name"],
        "status_code": resp.status_code,
    }

    if resp.status_code == 200:
        data = resp.json()
        result["success"] = True
        result["existing_languages"] = data.get("existing_languages", [])
        result["total_languages"] = data.get("total_languages")
        log("source_languages_ok", persona=p["name"],
            total=data.get("total_languages"),
            langs=[l["lang"] for l in data.get("existing_languages", [])])
    else:
        result["success"] = False
        result["error"] = resp.text[:200]
        log("source_languages_error", persona=p["name"], status=resp.status_code)

    return result


# ═══════════════════════════════════════════════════════════════════════════
# ETAPE 4 — TEST BY-SOURCE (deduplication)
# ═══════════════════════════════════════════════════════════════════════════


async def test_by_source(client: httpx.AsyncClient, p: dict) -> dict:
    """Verifie que le endpoint by-source regroupe les jobs par URL."""
    log("by_source_start", persona=p["name"])

    resp = await client.get(
        f"{API}/jobs/by-source",
        params={"source_url": p["source_url"]},
        timeout=10,
    )

    result = {"persona": p["name"], "status_code": resp.status_code}

    if resp.status_code == 200:
        data = resp.json()
        result["success"] = True
        result["jobs_count"] = len(data)
        result["languages"] = [j.get("target_lang") for j in data]
        log("by_source_ok", persona=p["name"], count=len(data), langs=result["languages"])
    else:
        result["success"] = False
        result["error"] = resp.text[:200]
        log("by_source_error", persona=p["name"], status=resp.status_code)

    return result


# ═══════════════════════════════════════════════════════════════════════════
# ETAPE 5 — TEST JOB STATUS (polling jusqu'a done)
# ═══════════════════════════════════════════════════════════════════════════


async def test_job_status(client: httpx.AsyncClient, job_id: str, persona: str, timeout_s: int = 600) -> dict:
    """Ping le status du job jusqu'a 'done' ou timeout."""
    log("status_poll_start", persona=persona, job_id=job_id[:8])
    t0 = time.monotonic()
    statuses = []

    while time.monotonic() - t0 < timeout_s:
        try:
            resp = await client.get(f"{API}/jobs/{job_id}/status", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                s = data.get("status", "unknown")
                if s not in ("queued", "unknown", "processing"):
                    elapsed = round(time.monotonic() - t0, 2)
                    result = {
                        "persona": persona,
                        "job_id": job_id[:8],
                        "final_status": s,
                        "total_wait_s": elapsed,
                        "status_history": statuses,
                        "duration_s": data.get("duration_s"),
                        "storage_url": data.get("storage_url", "")[:80] if data.get("storage_url") else None,
                        "source_lang": data.get("source_lang"),
                        "cost_breakdown": data.get("cost_breakdown"),
                    }
                    log("status_done", persona=persona, job_id=job_id[:8],
                        status=s, elapsed_s=elapsed)
                    return result
                statuses.append({"status": s, "elapsed_s": round(time.monotonic() - t0, 1)})
            elif resp.status_code == 404:
                await asyncio.sleep(2)
                continue
        except Exception as e:
            log("status_poll_error", persona=persona, job_id=job_id[:8], error=str(e)[:100])
        await asyncio.sleep(3)

    return {"persona": persona, "job_id": job_id[:8], "final_status": "timeout", "total_wait_s": timeout_s}


# ═══════════════════════════════════════════════════════════════════════════
# RAPPORT
# ═══════════════════════════════════════════════════════════════════════════


def generate_report(preflight_results, submit_results, source_lang_results, by_source_results, status_results):
    total = len(PERSONAS)
    preflight_ok = sum(1 for r in preflight_results if r.get("success"))
    submit_ok = sum(1 for r in submit_results if r.get("success"))
    source_ok = sum(1 for r in source_lang_results if r.get("success"))
    by_source_ok = sum(1 for r in by_source_results if r.get("success"))
    total_ok = sum(1 for r in status_results if r.get("final_status") in ("done", "queued"))

    report = {
        "test_suite": "personas-e2e",
        "timestamp": TIMESTAMP,
        "api_url": API,
        "summary": {
            "total_personas": total,
            "preflight_ok": f"{preflight_ok}/{total}",
            "submit_ok": f"{submit_ok}/{total}",
            "source_languages_ok": f"{source_ok}/{total}",
            "by_source_ok": f"{by_source_ok}/{total}",
            "jobs_completed": f"{total_ok}/{total}",
            "overall": "✅" if all([
                preflight_ok == total,
                submit_ok == total,
                source_ok == total,
                by_source_ok == total,
            ]) else "⚠️  PARTIEL",
        },
        "personas": [],
        "status_results": status_results,
    }

    for p in PERSONAS:
        pre = next((r for r in preflight_results if r["persona"] == p["name"]), {})
        sub = next((r for r in submit_results if r["persona"] == p["name"]), {})
        src = next((r for r in source_lang_results if r["persona"] == p["name"]), {})
        bys = next((r for r in by_source_results if r["persona"] == p["name"]), {})
        sta = next((r for r in status_results if r["persona"] == p["name"]), {})

        report["personas"].append({
            "name": p["name"],
            "description": p["description"],
            "options": {
                "source_url": p["source_url"][:60],
                "target_lang": p["target_lang"],
                "mode": p["mode"],
                "pool": p["pool"],
                "expected_queue": p["expected_queue"],
            },
            "results": {
                "preflight": {
                    "ok": pre.get("success"),
                    "duration_s": pre.get("duration_s"),
                    "cost": pre.get("cost"),
                },
                "submit": {
                    "ok": sub.get("success"),
                    "job_id": sub.get("job_id", sub.get("response", {}).get("job_id", ""))[:8] if sub.get("success") else None,
                    "multi_video": sub.get("multi_video", False),
                    "cached": sub.get("cached", sub.get("response", {}).get("cached", False)),
                },
                "source_languages": {"ok": src.get("success"), "total": src.get("total_languages")},
                "by_source": {"ok": bys.get("success"), "count": bys.get("jobs_count")},
                "job_status": {
                    "final": sta.get("final_status"),
                    "wait_s": sta.get("total_wait_s"),
                },
            },
        })

    return report


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════


async def main():
    log("suite_start", personas=[p["name"] for p in PERSONAS])

    async with httpx.AsyncClient(timeout=120) as client:
        # ── Health check ──
        try:
            r = await client.get(f"{API}/health", timeout=5)
            assert r.status_code == 200
            log("api_ok", url=API)
        except Exception as e:
            log("api_down", url=API, error=str(e)[:100])
            sys.exit(1)

        # ── Etape 1 : Preflight (tous en parallele) ──
        log("phase_start", phase="preflight")
        preflight_results = await asyncio.gather(*[
            test_preflight(client, p) for p in PERSONAS
        ])

        # ── Etape 2 : Source-languages (avant soumission) ──
        log("phase_start", phase="source_languages")
        source_lang_results = await asyncio.gather(*[
            test_source_languages(client, p) for p in PERSONAS
        ])

        # ── Etape 3 : By-source (deduplication) ──
        log("phase_start", phase="by_source")
        by_source_results = await asyncio.gather(*[
            test_by_source(client, p) for p in PERSONAS
        ])

        # ── Etape 4 : Soumission (en sequence pour eviter timeout yt-dlp) ──
        log("phase_start", phase="submit")
        submit_results = []
        for p in PERSONAS:
            # Attendre que yt-dlp soit libre (1 call a la fois)
            r = await test_submit(client, p)
            submit_results.append(r)
            await asyncio.sleep(0.5)

        # ── Etape 5 : Poll status (pour les jobs soumis) ──
        log("phase_start", phase="status_poll")
        status_tasks = []
        for r in submit_results:
            if r.get("success"):
                if r.get("multi_video"):
                    # Multi-video : suivre chaque sous-job
                    for j in r.get("jobs", []):
                        jid = j.get("job_id", "")
                        if jid:
                            status_tasks.append(
                                asyncio.create_task(test_job_status(
                                    client, jid, r["persona"] + f" (video {j.get('video_index', '?')})"
                                ))
                            )
                else:
                    jid = r.get("job_id", r.get("response", {}).get("job_id", ""))
                    if jid:
                        status_tasks.append(
                            asyncio.create_task(test_job_status(client, jid, r["persona"]))
                        )

        status_results = await asyncio.gather(*status_tasks, return_exceptions=True)
        status_results = [s if not isinstance(s, Exception) else {"error": str(s)[:200]} for s in status_results]

    # ── Rapport final ──
    log("phase_start", phase="report")
    report = generate_report(
        preflight_results, submit_results,
        source_lang_results, by_source_results,
        status_results,
    )

    report_path = OUT / f"e2e_personas_{TIMESTAMP}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    log("suite_complete", path=str(report_path), summary=report["summary"])

    # Console-friendly recap
    print("\n" + "=" * 60)
    print("RAPPORT E2E — 5 PERSONAS")
    print("=" * 60)
    for pdata in report["personas"]:
        r = pdata["results"]
        status_icon = "✅" if r["job_status"]["final"] in ("done", "queued") else "⏳" if r["job_status"]["final"] == "processing" else "❌"
        print(f"  {status_icon} {pdata['name']:8} | "
              f"preflight={'✅' if r['preflight']['ok'] else '❌'} "
              f"submit={'✅' if r['submit']['ok'] else '❌'} "
              f"source={'✅' if r['source_languages']['ok'] else '❌'} "
              f"status={r['job_status']['final'] or 'N/A'}"
              f"{' (' + str(r['job_status']['wait_s']) + 's)' if r['job_status'].get('wait_s') else ''}")
    print("=" * 60)
    print(f"Rapport detaille : {report_path}")
    print(f"Resume: {report['summary']['overall']}")


if __name__ == "__main__":
    asyncio.run(main())
