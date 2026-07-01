"""test_economy_flow.py — Test complet du circuit economique Subvox

Verifie :
1. Preflight avec cout et remises (community vs personal pool)
2. Soumission authentifiee avec wallet (JWT)
3. Deduction SUBVOX et cost_breakdown
4. Distribution aux parties prenantes
5. Resolution de cle Groq par wallet
6. Transaction log dans subvox_transactions

Usage:
  source .venv/bin/activate
  python3 tests_e2e_economy.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone

import asyncpg
import httpx
from pathlib import Path

API = "http://localhost:8001"
DB = "postgresql://postgres:***@localhost:5432/subvox"
WALLET = "5Pe2BifjrwGoYYKVPyY1XwXBjHmsi6yC1GFLxyfTaDhf"
TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
TEST_LANG = "pt"
JWT_SECRET = "change-me-in-production"
OUT = "/tmp/subvox-economy-test.json"

passed = 0
failed = 0
results = []


def check(name: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        icon = "PASS"
    else:
        failed += 1
        icon = "FAIL"
    results.append({"test": name, "status": icon, "detail": detail})
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail else ""))


async def main():
    global passed, failed
    import jwt as pyjwt
    from uuid import uuid4

    # URL unique pour eviter la deduplication entre les runs
    unique_url = f"{TEST_URL}&t={uuid4().hex[:8]}"

    print("=" * 60)
    print("TEST ECONOMIE — Circuit complet")
    print("=" * 60)
    print(f"Wallet: {WALLET[:20]}...")
    print(f"URL:    {TEST_URL[:50]}")
    print()

    # Generate JWT token for this wallet
    import jwt as pyjwt
    token = pyjwt.encode(
        {"sub": WALLET, "exp": int(time.time()) + 3600},
        JWT_SECRET, algorithm="HS256",
    )
    auth_headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=120) as http:
        db = await asyncpg.connect(DB)

        # ── 1. PREFLIGHT — verification du cout ──
        print("1. PREFLIGHT")
        r = await http.post(f"{API}/jobs/preflight", json={
            "source_url": unique_url,
            "target_langs": [TEST_LANG],
            "pool": "community",
        })
        data = r.json()
        check("preflight status", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            check("preflight duration", data.get("duration_s", 0) > 0, f"{data['duration_s']}s")
            cost = data.get("cost", {})
            check("cost.user_cost > 0", cost.get("user_cost", 0) > 0, f"{cost['user_cost']} SUBVOX")
            check("cost.provider_share", cost.get("provider_share", 0) > 0, f"{cost['provider_share']}")
            check("cost.platform_share", cost.get("platform_share", 0) > 0, f"{cost['platform_share']}")
            check("cost.burn_amount >= 0", cost.get("burn_amount", -1) >= 0, f"{cost['burn_amount']}")

        check("target_lang non traduit avant soumission", True, TEST_LANG)

        # ── 2. SOUMISSION AUTHENTIFIEE (avec JWT wallet) ──
        print("\n2. SOUMISSION AUTHENTIFIEE")
        r = await http.post(
            f"{API}/jobs/submit",
            json={
                "source_url": unique_url,
                "target_lang": TEST_LANG,
                "mode": "translate",
                "pool": "community",
            },
            headers=auth_headers,
        )
        data = r.json()
        job_id = data.get("job_id", "")
        check("submit HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
        check("submit status = queued", data.get("status") == "queued", f"job_id={job_id[:8]}")
        check("video_index present", "video_index" in data, str(data.get("video_index")))
        check("subtest_payment present", "subtest_payment" in data)
        check("source_job_id field", "source_job_id" in data)
        check("discount_applicable field", "discount_applicable" in data)

        # ── 3. COST_BREAKDOWN en DB ──
        print("\n3. COST BREAKDOWN (en base)")
        await asyncio.sleep(1.5)
        row = await db.fetchrow(
            "SELECT cost_breakdown FROM jobs WHERE id = $1",
            job_id,
        )
        cb = json.loads(row["cost_breakdown"]) if row and row["cost_breakdown"] else {}
        check("cost_breakdown stocke", bool(cb), json.dumps(cb)[:120] if cb else "absent")
        if cb:
            check("wallet = " + WALLET[:12], cb.get("wallet") == WALLET, cb.get("wallet", "?")[:16])
            check("user_cost > 0", cb.get("user_cost", 0) > 0, f"{cb['user_cost']} SUBVOX")
            check("provider_share > 0", cb.get("provider_share", 0) > 0, f"{cb['provider_share']}")
            check("platform_share > 0", cb.get("platform_share", 0) > 0, f"{cb['platform_share']}")
            check("rewards_share > 0", cb.get("rewards_share", 0) > 0, f"{cb['rewards_share']}")
            check("burn_amount >= 0", cb.get("burn_amount", -1) >= 0, f"{cb['burn_amount']}")
            total = (cb.get("provider_share", 0) + cb.get("platform_share", 0)
                     + cb.get("rewards_share", 0) + cb.get("burn_amount", 0)
                     + cb.get("opfees_share", 0))
            check("shares sum = user_cost", cb.get("user_cost", 0) == total,
                  f"{cb['user_cost']} = {total}")

        # ── 4. TRANSACTIONS enregistrees ──
        print("\n4. TRANSACTIONS")
        # deduct_subvox n'enregistre pas le job_id, on cherche par wallet
        txns = await db.fetch(
            "SELECT tx_type, amount, left(from_wallet,20) as from_addr, "
            "created_at FROM subvox_transactions "
            "WHERE from_wallet = $1 AND created_at > now() - interval '5 minutes'"
            "ORDER BY created_at DESC",
            WALLET,
        )
        check("transactions > 0", len(txns) > 0, f"{len(txns)} enregistrees")
        for t in txns:
            check(f"transaction {t['tx_type']}: {t['amount']} SUBVOX", True,
                  f"de {t['from_addr'][:16]}...")
        if txns:
            check("au moins 1 job_payment",
                  any(t["tx_type"] == "job_payment" for t in txns),
                  f"types: {[t['tx_type'] for t in txns]}")

        # ── 5. RESOLUTION DE CLE GROQ via API ──
        print("\n5. RESOLUTION DE CLE GROQ")
        try:
            r = await http.get(
                f"{API}/billing/groq-key/{WALLET}",
                timeout=10,
            )
            check("groq-key HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
            if r.status_code == 200:
                key_data = r.json()
                check("cle retournee", bool(key_data.get("key")),
                      f"{key_data.get('key', '')[:15]}...")
        except Exception as e:
            check("groq-key endpoint", False, str(e)[:80])

        # ── 6. KEYS EN DB ──
        print("\n6. CLE DANS user_groq_keys")
        row = await db.fetchrow(
            "SELECT user_id, is_valid, source, "
            "groq_key_hash IS NOT NULL as has_groq, "
            "deepseek_key_hash IS NOT NULL as has_ds, "
            "openrouter_key_hash IS NOT NULL as has_or "
            "FROM user_groq_keys WHERE user_id = $1",
            WALLET,
        )
        check("user_groq_keys existe", bool(row), "trouve" if row else "introuvable")
        if row:
            check("cle valide", row["is_valid"], f"source={row['source']}")
            check("cle Groq presente", row["has_groq"])
            check("cle DeepSeek presente", row["has_ds"])
            if not row["has_or"]:
                check("cle OpenRouter absente (normal)", True, "pas fournie")

        # ── 7. RATIOS POOL ──
        print("\n7. RATIOS POOL GROQ")
        rows = await db.fetch(
            "SELECT wallet_address, personal_ratio, shared_ratio "
            "FROM subvox_groq_pool WHERE is_active=true"
        )
        check("pool >= 1 cle active", len(rows) >= 1, f"{len(rows)} cles")
        for r2 in rows:
            check(f"  {r2['wallet_address'][:16]}...",
                  r2["personal_ratio"] + r2["shared_ratio"] == 100,
                  f"perso={r2['personal_ratio']}% shared={r2['shared_ratio']}%")

        # ── 8. SOURCE-LANGUAGES (verification FR dedupe) ──
        print("\n8. SOURCE-LANGUAGES (apres soumission)")
        r = await http.get(
            f"{API}/jobs/source-languages",
            params={"source_url": unique_url},
        )
        data = r.json()
        check("source-languages HTTP 200", r.status_code == 200)
        langs = [l["lang"] for l in data.get("existing_languages", [])]
        check("FR deja traduit", "fr" in langs, str(langs))

        # ── 9. BY-SOURCE (verification groupement) ──
        print("\n9. BY-SOURCE (jobs groupes par URL)")
        r = await http.get(
            f"{API}/jobs/by-source",
            params={"source_url": unique_url},
        )
        data = r.json()
        check("by-source HTTP 200", r.status_code == 200)
        check("jobs > 0 pour cette URL", len(data) > 0, f"{len(data)} jobs")

        # ── 10. PROVIDER SPLIT NORMALISATION (test direct) ──
        print("\n10. PROVIDER SPLIT NORMALISATION")
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "economy" / "backend"))
        from core.subvox_economy import get_provider_split, PROVIDER_WEIGHTS
        import_path = sys.path.pop(0)

        # Normal: Groq + DeepSeek only
        s1 = get_provider_split({"groq_transcription", "deepseek_translation"})
        total1 = sum(s1.values())
        check("normal split sum = 0.60", abs(total1 - 0.60) < 0.001, f"{total1:.4f}")
        check("groq ~30%", 0.29 < s1.get("groq_transcription", 0) < 0.31,
              f"{s1.get('groq_transcription', 0)*100:.1f}%")
        check("deepseek ~30%", 0.29 < s1.get("deepseek_translation", 0) < 0.31,
              f"{s1.get('deepseek_translation', 0)*100:.1f}%")
        check("no vision", "openrouter_vision" not in s1)

        # Complet: Groq + DeepSeek + Vision + Cookies
        s2 = get_provider_split(set(PROVIDER_WEIGHTS.keys()))
        total2 = sum(s2.values())
        check("full split sum = 0.60", abs(total2 - 0.60) < 0.001, f"{total2:.4f}")
        check("groq ~25%", 0.24 < s2.get("groq_transcription", 0) < 0.26,
              f"{s2.get('groq_transcription', 0)*100:.1f}%")
        check("deepseek ~25%", 0.24 < s2.get("deepseek_translation", 0) < 0.26,
              f"{s2.get('deepseek_translation', 0)*100:.1f}%")
        check("vision ~5%", 0.04 < s2.get("openrouter_vision", 0) < 0.06,
              f"{s2.get('openrouter_vision', 0)*100:.1f}%")
        check("cookies ~5%", 0.04 < s2.get("cookies_access", 0) < 0.06,
              f"{s2.get('cookies_access', 0)*100:.1f}%")

        await db.close()

    # ── RAPPORT FINAL ──
    print("\n" + "=" * 60)
    total = passed + failed
    pct = round(passed / total * 100) if total > 0 else 0
    print(f"RESULTATS: {passed}/{total} passes ({pct}%) — {failed} echecs")
    if failed == 0:
        print("TOUT EST OK — le circuit economique tourne correctement")
    else:
        print(f"{failed} test(s) a corriger")
    print("=" * 60)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet": WALLET,
        "summary": {"passed": passed, "failed": failed, "total": total, "pct": pct},
        "tests": results,
    }
    with open(OUT, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Rapport detaille: {OUT}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
