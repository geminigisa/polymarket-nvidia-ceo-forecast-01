# Optimasi V2 — polymarket-nvidia-ceo-forecast-01

Branch: `optimization-v2` (dari V1 `a0033d1`). **V1 di `master` tidak tersentuh.**
`main.py` di branch ini = V1 yang sama (sha256 `c2ddaa76…`). Kandidat V2 ada di
`main_v2.py` terpisah; `main_v1_backup.py` adalah salinan V1 tanpa perubahan.

## Jawaban tegas

| Pertanyaan | Jawaban |
|---|---|
| Kelemahan terbesar V1? | **MAD collapse.** MAD dari SEMUA gerakan (termasuk nol) = 0 di 57,1% pasangan (market, lag) → skala `s` jatuh ke floor 0,0001, forecast nyaris degenerat, \|drift\|/s meledak (p99 16,7), dan 16,43% baris tidak monoton sebelum `sorted()` (kuantil 95% sempat di bawah kuantil 25%). |
| Perubahan mana yang benar-benar meningkatkan skor? | (1) **B1: MAD gerakan NONZERO saja, tanpa koreksi `/sqrt(1-p0)`, S_SCALE 0,50** → 0,288800, menang 6/6 case. (2) **D1: regime scale** 0,8 stagnan / 1,0 normal / 1,3 jump (dari histori saja) → di atas B1 jadi 0,286869, menang 6/6 lagi. Yang TIDAK meningkatkan: koreksi batas atom-zero (V2-A kalah), Student-t (membantu di basis V1, merugikan di basis B1), empiris residual (kalah besar), asimetris (kalah), Laplace (seri). |
| Skor V2 vs V1? | **V2-Final 0,286869 vs V1 0,292874 → −0,006005 (−2,05%)**, vs house baseline 0,363589 → −21,1%. Per case: p00 0,4546, p01 0,3148, p02 0,3652, p03 0,3404, p04 0,1934, p05 0,1122 — menang SEMUA 6 case vs V1 dan vs B1. |
| Konsisten out-of-sample? | Konsisten di practice (6/6 case, 2 komponen yang masing-masing tervalidasi terpisah), TAPI practice bukan panduan final (RULES.txt tegas). Gain −2,05% di practice tidak menjamin final. Yang memberi keyakinan: ini perbaikan estimator yang benar (bukan tuning angka buta) + menang di semua case, bukan 1–2 case. |
| Runtime < 8 detik? | Ya, jauh: **0,99 detik untuk 6 case (~0,165 dtk/case)**, deterministik byte-identik 2 run, skema valid, output ≤ 277 KB. |
| V2 layak gantikan V1? | **Ya, sebagai kandidat — dengan satu syarat prosedural (lihat di bawah).** Secara statistik V2-Final layak promosi. Secara prosedur, promosi ke `main.py` + submit HANYA oleh parent/user, dan sebaiknya lewat sesi fresh (alasan di bawah). |

## Tabel Champion vs Challenger (mean pinball, 6 practice case)

| Model | Mean | Δ vs V1 | Menang vs V1 |
|---|---:|---:|---:|
| House Baseline | 0,363589 | — | Reference |
| **V1 (Champion)** | **0,292874** | — | — |
| V2-A atom bounds benar | 0,294628 | +0,0018 | 1/6 — JANGAN promosikan |
| C3 empiris residual | 0,359215 | +0,0663 | 0/6 |
| C4 asimetris | 0,309579 | +0,0167 | 0/6 |
| C1 Student-t df=5 (basis V1) | 0,292547 | −0,0003 | 3/6 |
| C2 Laplace | 0,292878 | +0,0000 | seri |
| D1 regime (basis V1) | 0,291936 | −0,0009 | 4/6 |
| D3 D1+D2a | 0,291850 | −0,0010 | 5/6 |
| X D1+t5 (basis V1) | 0,291270 | −0,0016 | 5/6 |
| B1 MAD-nonzero s=0,50 | 0,288800 | −0,0041 | 6/6 |
| B1+D1+t5 s=0,55 | 0,286511 | −0,0064 | 6/6 vs V1, tapi 4/6 vs B1+D1 — noise, TIDAK dipakai |
| **V2-Final = B1+D1** | **0,286869** | **−0,0060** | **6/6** |

Detail lengkap (semua varian, sweep, per-kuantil, per-horizon): `experiment_results.json`,
`../v2-work/audit/REPORT.md`, `../v2-work/exp/REPORT.md`.

## Mengapa batas atom-zero yang "benar" kalah (temuan audit)

V1 memakai `lo=(1-p0)*0,5` — hanya eksak bila drift=0. Batas eksak
`lo=(1-p0)*Phi(-drift/s)` terbukti benar oleh unit test (34/34 PASS), dan
|drift|/s di practice memang besar. Tapi memperbaikinya menggeser median
keluar dari harga terakhir di 35,5% baris dan merugikan kuantil 50% sebesar
+0,0075 — karena drift (mean-reversion) terlalu misspecified untuk jadi
pusat median. Pelajaran: batas simetris V1 adalah regularisasi yang
menguntungkan, bukan sekadar bug. **Jangan "perbaiki" batas atom tanpa bukti
baru.** V2-Final sengaja mempertahankannya.

## Apa yang diubah V2-Final vs V1 (hanya 2 hal)

1. `s = 1.4826 * MAD_nonzero * 0,50` (V1: `1.4826 * MAD_semua / sqrt(1-p0) * 0,60`).
   Floor-hit turun dari 57,1% menjadi 0,3% pasangan (market, lag).
2. `s *= regime_scale`: 0,8 bila stagnan (p0 lag-1 > 0,9), 1,3 bila jump
   (gerakan > 0,05 dalam 60 menit terakhir ATAU p0 lag-1 < 0,5), else 1,0.
   Semua dari histori sampai checkpoint saja — tanpa info masa depan.

Selain itu identik dengan V1: lag, interpolasi log-horizon, mean-reversion
tau 1200 ke median 24 jam, p0 clamp [0,02, 0,9], fallback, clamp/round/sort.

## Langkah promosi (parent/user yang putuskan — JANGAN dilakukan sendiri)

1. Putuskan: promosikan `main_v2.py` menjadi `main.py` (V2-Final), atau
   submit V1 saja. Bila ragu, V1 (0,292874) sudah mengalahkan baseline
   dengan margin besar dan tetap aman sebagai cadangan.
2. **PENTING — transcript gate:** `main_v2.py` di branch ini disusun dari
   kandidat worker + patch koordinator, BUKAN ditulis fresh lewat write-tool
   dalam satu sesi yang tidak pernah membaca V1. Untuk submit, cara bersihnya:
   sesi FRESH yang belum pernah membaca `main.py` V1 menulis ulang file
   entrypoint dari desain di atas (2+ pesan write/edit, mengikuti
   `~/workspace/custom-skills/makefun_bounty/SKILL.md`), lalu bundle +
   check + submit seperti V1. Jangan sekadar `cp`/`mv` file ini menjadi
   `main.py` lalu submit — risiko gagal `thinking_reproduces`.
3. Sebelum submit apa pun: re-bundle transkrip dengan usage rows terbaru,
   jalankan `check` sampai `thinking_priced` lolos, dan submit sebelum
   deadline **2026-11-13 21:00 UTC (2026-11-14 04:00 WIB)**. Kuota: 0 entry
   terpakai di kompetisi ini; praktis maks 3 submit.
