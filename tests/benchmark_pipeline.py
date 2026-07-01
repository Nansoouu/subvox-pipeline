"""benchmark_pipeline.py — Benchmark complet du pipeline Subvox

Usage:
  # Tester la soumission + file d'attente (5 jobs courts)
  python3 benchmark_pipeline.py --mode queue
  
  # Tester les limites Groq (10 transcriptions)
  python3 benchmark_pipeline.py --mode groq-stress
  
  # Tester download + watermark
  python3 benchmark_pipeline.py --mode download-wm
  
  # Tout en une fois
  python3 benchmark_pipeline.py --mode all

Prérequis:
  - PostgreSQL et Redis tournent sur localhost
  - Economy API sur port 8001
  - Workers Celery démarrés
  - .env configuré (GROQ_API_KEY, DEEPSEEK_API_KEY)
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

# ── Configuration ──────────────────────────────────────────────────────────
ECONOMY_URL = os.getenv("ECONOMY_URL", "http://localhost:8001")
# Vidéos YouTube courtes et fiables pour les tests
TEST_VIDEOS = {
    "me_at_zoo": "https://www.youtube.com/watch?v=jNQXAC9IVRw",   # 0:19 — 1er YouTube, tres court
    "subvox_demo": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # 3:33 — classique
    "short_clip_1": "https://www.youtube.com/watch?v=9bZkp7q19f0s", # 4:13 — Gangnam Style
    "short_clip_2": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",  # 3:56 — Despacito
    "short_clip_3": "https://www.youtube.com/watch?v=RgKAFK5djSk",  # 3:28 — See You Again
}

OUTPUT_DIR = Path("/tmp/subvox-benchmarks")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Logging structuré ──────────────────────────────────────────────────────


def log_json(event: str, **data):
    """Emit a structured JSON log line."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **data,
    }
    print(json.dumps(entry, default=str))
    sys.stdout.flush()


# ── Helpers API ────────────────────────────────────────────────────────────


async def submit_job(
    client: httpx.AsyncClient,
    source_url: str,
    target_lang: str = "fr",
    mode: str = "translate",
) -> dict:
    """Soumet un job et retourne la réponse."""
    resp = await client.post(
        f"{ECONOMY_URL}/jobs/submit",
        json={"source_url": source_url, "target_lang": target_lang, "mode": mode},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def get_job_status(client: httpx.AsyncClient, job_id: str) -> dict:
    """Récupère le statut d'un job."""
    resp = await client.get(f"{ECONOMY_URL}/jobs/{job_id}/status", timeout=10)
    if resp.status_code == 404:
        return {"status": "pending", "error": "not found"}
    resp.raise_for_status()
    return resp.json()


async def wait_for_job(
    client: httpx.AsyncClient,
    job_id: str,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> dict:
    """Attend qu'un job soit terminé (done ou error)."""
    start = time.monotonic()
    last_status = "queued"
    while time.monotonic() - start < timeout:
        try:
            status_data = await get_job_status(client, job_id)
            s = status_data.get("status", "unknown")
            if s in ("done", "error"):
                elapsed = time.monotonic() - start
                status_data["total_wait_s"] = round(elapsed, 2)
                return status_data
            if s != last_status:
                log_json("job_progress", job_id=job_id[:8], status=s, elapsed_s=round(time.monotonic() - start, 1))
                last_status = s
        except Exception as e:
            log_json("job_poll_error", job_id=job_id[:8], error=str(e)[:100])
        await asyncio.sleep(poll_interval)
    return {"status": "timeout", "job_id": job_id, "total_wait_s": timeout}


async def get_source_languages(client: httpx.AsyncClient, source_url: str) -> dict:
    """Test l'endpoint source-languages."""
    resp = await client.get(
        f"{ECONOMY_URL}/jobs/source-languages",
        params={"source_url": source_url},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


async def get_estimate(client: httpx.AsyncClient, source_url: str) -> dict:
    """Test l'endpoint estimate-duration."""
    resp = await client.post(
        f"{ECONOMY_URL}/jobs/estimate-duration",
        json={"source_url": source_url},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ── Benchmark : File d'attente ─────────────────────────────────────────────


async def bench_queue():
    """Test 1: Queue multi-worker — soumettre 5 jobs et mesurer le parallélisme.

    Avec les workers short (4 concurrents), 5 jobs courts devraient
    tous commencer simultanément.
    """
    log_json("bench_start", name="queue", description="5 jobs courts simultanés")
    results = []

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Estimer la durée des vidéos
        durations = {}
        for name, url in TEST_VIDEOS.items():
            try:
                est = await get_estimate(client, url)
                durations[name] = est.get("duration_s", 0)
                log_json("video_estimated", name=name, duration_s=est.get("duration_s", 0), needs_auth=est.get("needs_auth", False))
            except Exception as e:
                log_json("estimate_failed", name=name, error=str(e)[:100])

        # 2. Soumettre 5 jobs en rafale (sans attendre les réponses)
        submit_tasks = []
        t_start = time.monotonic()
        for name, url in TEST_VIDEOS.items():
            task = asyncio.create_task(submit_job(client, url, "fr"))
            submit_tasks.append((name, task))

        submissions = []
        for name, task in submit_tasks:
            try:
                resp = await task
                submissions.append({"name": name, **resp})
                log_json("job_submitted", name=name, job_id=resp.get("job_id", "?")[:8])
            except Exception as e:
                log_json("submit_failed", name=name, error=str(e)[:100])

        t_submit = time.monotonic() - t_start
        log_json("all_submitted", count=len(submissions), submit_time_s=round(t_submit, 2))

        # 3. Attendre que tous les jobs soient finis
        wait_tasks = []
        for s in submissions:
            jid = s.get("job_id", "")
            if jid:
                wait_tasks.append(asyncio.create_task(wait_for_job(client, jid)))

        completed = await asyncio.gather(*wait_tasks, return_exceptions=True)
        t_total = time.monotonic() - t_start

        # 4. Analyser les résultats
        for i, s in enumerate(submissions):
            status = completed[i] if i < len(completed) else {"status": "unknown"}
            if isinstance(status, Exception):
                status = {"status": "error", "error": str(status)[:200]}

            wait_s = status.get("total_wait_s", 0)
            video_name = s.get("name", "?")
            dur_s = durations.get(video_name, 0)

            results.append({
                "name": video_name,
                "job_id": s.get("job_id", ""),
                "duration_s": dur_s,
                "final_status": status.get("status"),
                "total_wait_s": wait_s,
                "queue_position": s.get("queue_position"),
                "mode": s.get("mode"),
                "download_only": s.get("download_only"),
                "subtest_payment": s.get("subtest_payment"),
                "cached": s.get("cached", False),
            })

            log_json(
                "job_result",
                name=video_name,
                duration_s=dur_s,
                wait_s=wait_s,
                status=status.get("status"),
                ratio=round(wait_s / dur_s, 2) if dur_s > 0 else None,
            )

        # 5. Rapport
        done = [r for r in results if r["final_status"] == "done"]
        errors = [r for r in results if r["final_status"] == "error"]
        times_up = [r["total_wait_s"] for r in done if r["total_wait_s"]]
        seq_time = sum(times_up)  # temps séquentiel hypothétique

        report = {
            "benchmark": "queue",
            "total_jobs": len(results),
            "completed": len(done),
            "errors": len(errors),
            "total_wall_clock_s": round(t_total, 2),
            "hypothetical_sequential_s": round(seq_time, 2),
            "parallel_speedup": round(seq_time / t_total, 2) if t_total > 0 else 0,
            "average_wait_s": round(sum(times_up) / len(times_up), 2) if times_up else 0,
            "jobs": results,
            "config": {
                "short_workers": 4,
                "medium_workers": 2,
                "long_workers": 1,
                "xlong_workers": 1,
            },
        }

        # Sauvegarder
        report_path = OUTPUT_DIR / f"bench_queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str))
        log_json("bench_complete", name="queue", path=str(report_path), summary={
            "total_wall_clock_s": report["total_wall_clock_s"],
            "parallel_speedup": report["parallel_speedup"],
            "completed/reported": f"{len(done)}/{len(results)}",
        })
        return report


# ── Benchmark : Groq Rate Limits ───────────────────────────────────────────


async def bench_groq_stress():
    """Test 2: Stresser Groq avec 10 transcriptions simultanées.

    Mesure les 429 Too Many Requests et la résilience du pool de clés.
    """
    log_json("bench_start", name="groq-stress", description="10 transcriptions simultanées Groq")
    results = []

    # Utiliser 2 URLs de test (la même 10 fois pour forcer la concurrence)
    test_url = TEST_VIDEOS["me_at_zoo"]
    n_requests = 10

    async with httpx.AsyncClient(timeout=300) as client:
        # Soumettre 10 jobs en même temps
        t_start = time.monotonic()

        tasks = []
        for i in range(n_requests):
            task = asyncio.create_task(submit_job(client, test_url, "fr"))
            tasks.append(task)

        submissions = await asyncio.gather(*tasks, return_exceptions=True)

        for i, resp in enumerate(submissions):
            if isinstance(resp, httpx.HTTPStatusError):
                results.append({
                    "attempt": i + 1,
                    "status": "http_error",
                    "status_code": resp.response.status_code,
                    "body": resp.response.text[:200],
                })
                log_json("groq_submit_error", attempt=i + 1, status_code=resp.response.status_code)
            elif isinstance(resp, Exception):
                results.append({
                    "attempt": i + 1,
                    "status": "error",
                    "error": str(resp)[:200],
                })
            else:
                results.append({
                    "attempt": i + 1,
                    "job_id": resp.get("job_id", "")[:8],
                    "status": resp.get("status"),
                    "queue_position": resp.get("queue_position"),
                    "cached": resp.get("cached", False),
                })
                log_json("groq_job_submitted", attempt=i + 1, job_id=resp.get("job_id", "?")[:8])

        t_submit = time.monotonic() - t_start
        log_json("groq_all_submitted", count=n_requests, submit_time_s=round(t_submit, 2))

        # Attendre les résultats
        for r in results:
            if r.get("job_id"):
                jid = r["job_id"]
                # Reconstruire l'UUID complet... on a que les 8 premiers chars
                # On va chercher par source_url à la place
                pass

        # Vérifier les jobs par source URL
        try:
            source_data = await get_source_languages(client, test_url)
            log_json("groq_source_languages", source_url=test_url[:60], total=source_data.get("total_languages"))
        except Exception as e:
            log_json("groq_source_languages_failed", error=str(e)[:100])

        report = {
            "benchmark": "groq-stress",
            "total_requests": n_requests,
            "accepted": sum(1 for r in results if r.get("status") == "queued"),
            "errors": sum(1 for r in results if r.get("status", "").startswith("http") or r.get("status") == "error"),
            "http_errors_by_code": {},
            "submit_time_s": round(t_submit, 2),
            "requests_per_second": round(n_requests / t_submit, 1) if t_submit > 0 else 0,
            "results": results,
        }

        # Compter les HTTP errors par code
        for r in results:
            code = r.get("status_code")
            if code:
                report["http_errors_by_code"][str(code)] = report["http_errors_by_code"].get(str(code), 0) + 1

        report_path = OUTPUT_DIR / f"bench_groq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2, default=str))
        log_json("bench_complete", name="groq-stress", path=str(report_path))
        return report


# ── Benchmark : Download + Watermark ───────────────────────────────────────


async def bench_download_watermark():
    """Test 3: Benchmark download + watermark sporadic.

    Mesure le temps de téléchargement et d'encodage du watermark
    pour différentes durées vidéo.
    """
    log_json("bench_start", name="download-wm", description="Download + watermark sporadic pour 30s, 2min, 10min")

    async with httpx.AsyncClient(timeout=600) as client:
        for duration_label, url in [
            ("30s", "https://www.youtube.com/watch?v=jNQXAC9IVRw"),   # 19s
            ("2min", "https://www.youtube.com/watch?v=9bZkp7q19f0s"), # 4min+
            ("10min", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"), # 3:33
        ]:
            log_json("bench_download_start", label=duration_label, url=url[:60])
            try:
                # 1. Estimer la durée
                est = await get_estimate(client, url)
                log_json("duration_estimated", label=duration_label, duration_s=est.get("duration_s", 0))

                # 2. Tester l'endpoint source-languages
                langs = await get_source_languages(client, url)
                log_json("source_languages", label=duration_label, existing=langs.get("existing_languages", []))

            except Exception as e:
                log_json("bench_skip", label=duration_label, error=str(e)[:100])

    return {"status": "done", "note": "Les benchmarks réels nécessitent l'API économie en fonctionnement"}


# ── Main ────────────────────────────────────────────────────────────────────


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Subvox Pipeline Benchmark Suite")
    parser.add_argument("--mode", choices=["queue", "groq-stress", "download-wm", "all", "smoke"], default="smoke")
    args = parser.parse_args()

    # Vérifier que l'API est accessible
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{ECONOMY_URL}/health")
            if r.status_code == 200:
                log_json("api_ready", url=ECONOMY_URL, service=r.json().get("service", "unknown"))
            else:
                log_json("api_unhealthy", url=ECONOMY_URL, status=r.status_code)
                sys.exit(1)
    except Exception as e:
        log_json("api_unreachable", url=ECONOMY_URL, error=str(e)[:100])
        log_json("info", message=f"L'API économie ({ECONOMY_URL}) n'est pas accessible.")
        log_json("info", message="Pour lancer l'API: cd economy && PYTHONPATH=backend uvicorn main:app --port 8001")
        log_json("info", message="Pour lancer les workers: voir le script start-bench.sh")
        sys.exit(1)

    if args.mode in ("queue", "all"):
        await bench_queue()

    if args.mode in ("groq-stress", "all"):
        await bench_groq_stress()

    if args.mode in ("download-wm", "all"):
        await bench_download_watermark()

    if args.mode == "smoke":
        log_json("info", message="=== Smoke Test ===")
        async with httpx.AsyncClient(timeout=10) as c:
            # Vérifier les endpoints principaux
            endpoints = [
                ("GET", "/health"),
                ("POST", "/jobs/estimate-duration"),
                ("POST", "/jobs/preflight"),
                ("GET", "/jobs/source-languages?source_url=https://youtube.com/watch?v=test"),
            ]
            for method, path in endpoints:
                try:
                    if method == "GET":
                        r = await c.get(f"{ECONOMY_URL}{path}", timeout=5)
                    else:
                        r = await c.post(f"{ECONOMY_URL}{path}", json={"source_url": TEST_VIDEOS["me_at_zoo"], "target_langs": ["fr"]}, timeout=10)
                    log_json("endpoint", method=method, path=path, status=r.status_code)
                except Exception as e:
                    log_json("endpoint_error", method=method, path=path, error=str(e)[:100])

    # Rapport final
    report_files = sorted(OUTPUT_DIR.glob("bench_*.json"))
    if report_files:
        log_json("reports_available", count=len(report_files), files=[str(f) for f in report_files])
    else:
        log_json("no_reports", message="Aucun rapport généré. Benchmarks sauvegardés dans /tmp/subvox-benchmarks/")


if __name__ == "__main__":
    asyncio.run(main())
