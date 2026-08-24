"""Run tutorial notebooks by part/section prefix.

Usage:
    python run_notebooks.py part0          # run all part0 notebooks
    python run_notebooks.py part2_01 part2_02  # run specific sections in order
    python run_notebooks.py part1          # run all part1 notebooks

Notebooks within each section are sorted and run sequentially.
Sections are run in the order given on the command line.
"""
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

TUTORIALS = Path(__file__).resolve().parent.parent / "tutorials"
TIMEOUT = 1800  # 30 minutes per notebook

# Sections and individual notebooks to skip during testing.
# NB: part2_08_opt is NOT skipped - the part2_08_sqp notebooks reuse its template
# directories, so the opt notebooks must run first (sections run in sorted order,
# and "part2_08_opt" sorts before "part2_08_sqp").
SKIP_SECTIONS = {
    "part2_07_da",
    "part2_09_mou",
}
SKIP_NOTEBOOKS = {
    # interactive widgets don't work in headless CI
    "understanding_variograms_and_realizations.ipynb",
    "intro_to_svd.ipynb",
    "simple_bayes_demo.ipynb",
    "intro_to_bayes.ipynb",
    "intro_to_regression.ipynb",
    # ies notebooks incompatible with reduced noptmax
    "freyberg_ies_2_localization.ipynb",
    "freyberg_ies_3_restarting.ipynb",
}

# Response-matrix / Jacobian builders (and their dependents) are the most expensive
# notebooks and run much slower on the macOS and Windows GitHub Actions runners, so we
# skip them there and rely on the Ubuntu job for coverage.  freyberg_fosm_and_dataworth
# is included because it loads the prior covariance from master_glm_1.
SKIP_ON_MAC_WIN = {
    "freyberg_glm_1.ipynb",
    "freyberg_glm_2.ipynb",
    "freyberg_glm_response_surface.ipynb",
    "freyberg_glm_response_surface_ies.ipynb",
    "freyberg_fosm_and_dataworth.ipynb",
}
# GitHub Actions sets RUNNER_OS; fall back to platform detection for local runs.
_RUNNER_OS = os.environ.get("RUNNER_OS", "")
IS_MAC_WIN = _RUNNER_OS in ("Windows", "macOS") or (
    not _RUNNER_OS and platform.system() in ("Darwin", "Windows")
)

# Ordering within sections where it matters.
# Keys are section directory prefixes; values are ordered notebook filenames.
# Sections not listed here have their notebooks sorted alphabetically.
SECTION_ORDER = {
    "part1_07_pilotpoints_setup": [
        "freyberg_pilotpoints_1_setup.ipynb",
    ],
    "part1_08_pilotpoints_run": [
        "freyberg_pilotpoints_2_run.ipynb",
    ],
    "part1_10_intro_to_fosm": [
        "intro_to_fosm.ipynb",
    ],
    "part2_01_pstfrom_pest_setup": [
        "freyberg_pstfrom_pest_setup.ipynb",
    ],
    "part2_02_obs_and_weights": [
        "freyberg_obs_and_weights.ipynb",
        "weights_vs_noise.ipynb",
    ],
    "part2_04_glm": [
        "freyberg_glm_1.ipynb",
        "freyberg_glm_2.ipynb",
    ],
    "part2_06_ies": [
        "freyberg_ies_1_basics.ipynb",
        "freyberg_ies_2_localization.ipynb",
        "freyberg_ies_3_restarting.ipynb",
        "freyberg_ies_4_noise.ipynb",
    ],
    "part2_07_da": [
        "freyberg_da_prep.ipynb",
        "freyberg_da_run.ipynb",
    ],
    "part2_08_opt": [
        "simple_LP_example.ipynb",
        "freyberg_opt_1.ipynb",
        "freyberg_opt_2.ipynb",
    ],
    "part2_09_mou": [
        "freyberg_mou_1.ipynb",
        "freyberg_mou_2.ipynb",
        "mou_viz.ipynb",
    ],
    "part2_10_eva_and_dsi": [
        "1_freyberg_ensemble_dataworth.ipynb",
        "2_freyberg_ensemble_data_space_inversion.ipynb",
    ],
}

# Part1 section run order. Order matters because later sections reuse results from
# earlier ones: part1_10 (fosm) needs the pilotpoints runs, and part1_14 (dsi) uses
# the prior ensemble that part1_13 (ies) leaves in its master directory.
PART1_ORDER = [
    "part1_01", "part1_02", "part1_03", "part1_04", "part1_05",
    "part1_06", "part1_07", "part1_08", "part1_09", "part1_10",
    "part1_11", "part1_12", "part1_13", "part1_14",
]


def get_sections(prefix):
    """Find tutorial section directories matching a prefix."""
    sections = sorted(
        d for d in TUTORIALS.iterdir()
        if d.is_dir() and d.name.startswith(prefix)
        and d.name not in SKIP_SECTIONS
    )
    return sections


def get_notebooks(section_dir):
    """Get ordered list of notebooks for a section directory."""
    dirname = section_dir.name
    if dirname in SECTION_ORDER:
        nbs = [
            section_dir / nb for nb in SECTION_ORDER[dirname]
            if (section_dir / nb).exists() and nb not in SKIP_NOTEBOOKS
        ]
    else:
        nbs = sorted(
            nb for nb in section_dir.glob("*.ipynb")
            if nb.name not in SKIP_NOTEBOOKS
        )
    if IS_MAC_WIN:
        nbs = [nb for nb in nbs if nb.name not in SKIP_ON_MAC_WIN]
    return nbs


def patch_ies_notebook(nb_path):
    """Patch IES notebooks to use fewer realizations and iterations for CI."""
    import json
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    changed = False
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        new_source = []
        for line in cell["source"]:
            orig = line
            if "ies_num_reals" in line and "=" in line and not line.lstrip().startswith("#"):
                # Replace any ies_num_reals assignment value with 20
                import re
                line = re.sub(
                    r'(ies_num_reals["\']?\s*[\])]?\s*=\s*)\d+',
                    r'\g<1>20', line
                )
            if "noptmax" in line and "=" in line and not line.lstrip().startswith("#"):
                # Replace positive noptmax values with 1, leave -1 and -2 alone
                import re
                line = re.sub(
                    r'(noptmax\s*=\s*)([2-9]\d*|[1-9]\d+)',
                    r'\g<1>3', line
                )
            if line != orig:
                changed = True
            new_source.append(line)
        cell["source"] = new_source
    if changed:
        with open(nb_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)
        print(f"  Patched IES settings in {nb_path.name}")
    return changed


def patch_part1_ies_notebook(nb_path):
    """Patch the part1 basic-ies notebook to run cheaply in CI: cap ensemble size at
    20 realizations (both the gaussian-draw `num_reals=` and `ies_num_reals`) and cap
    positive noptmax at 2 iterations (leaving 0/1 and any negative values untouched).
    Returns True if the notebook was changed."""
    import json
    import re
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    def cap_noptmax(m):
        return m.group(1) + (m.group(2) if int(m.group(2)) <= 2 else "2")

    changed = False
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        new_source = []
        for line in cell["source"]:
            orig = line
            if line.lstrip().startswith("#"):
                new_source.append(line)
                continue
            # ies_num_reals = N  and  num_reals=N (gaussian draw) -> 20
            if "ies_num_reals" in line and "=" in line:
                line = re.sub(r'(ies_num_reals["\']?\s*[\])]?\s*=\s*)\d+',
                              r'\g<1>20', line)
            elif "num_reals" in line and "=" in line:
                line = re.sub(r'(num_reals\s*=\s*)\d+', r'\g<1>20', line)
            # positive noptmax -> capped at 2 (0/1 and negatives left alone)
            if "noptmax" in line and "=" in line:
                line = re.sub(r'(noptmax\s*=\s*)(\d+)', cap_noptmax, line)
            if line != orig:
                changed = True
            new_source.append(line)
        cell["source"] = new_source
    if changed:
        with open(nb_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)
        print(f"  Patched part1 IES settings in {nb_path.name}")
    return changed


def patch_noptmax(nb_path, value):
    """Set positive noptmax assignments to `value` (leaving 0 and negative values,
    e.g. -1/-2 Jacobian-only runs, untouched). Used to shorten expensive GLM runs
    in CI. Returns True if the notebook was changed."""
    import json
    import re
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    changed = False
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        new_source = []
        for line in cell["source"]:
            orig = line
            if "noptmax" in line and "=" in line and not line.lstrip().startswith("#"):
                line = re.sub(r'(noptmax\s*=\s*)([1-9]\d*)',
                              r'\g<1>{0}'.format(value), line)
            if line != orig:
                changed = True
            new_source.append(line)
        cell["source"] = new_source
    if changed:
        with open(nb_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)
        print(f"  Set noptmax={value} in {nb_path.name}")
    return changed


def uses_panther(nb):
    """Return True if any code cell in the loaded notebook invokes start_workers."""
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        for line in cell["source"]:
            if "start_workers" in line and not line.lstrip().startswith("#"):
                return True
    return False


def patch_overdue_giveup_fac(nb_path):
    """Inject overdue_giveup_fac=1e10 before each pst.write call in notebooks that
    use the panther parallel run manager. Avoids spurious agent timeouts on slow
    runners (e.g. GitHub Actions macOS)."""
    import json
    import re
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    if not uses_panther(nb):
        return False
    changed = False
    pattern = re.compile(r'^(\s*)pst\.write\(')
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        new_source = []
        for line in cell["source"]:
            stripped = line.lstrip()
            if not stripped.startswith("#"):
                m = pattern.match(line)
                if m:
                    indent = m.group(1)
                    new_source.append(
                        f'{indent}pst.pestpp_options["overdue_giveup_fac"] = 1e10\n'
                    )
                    changed = True
            new_source.append(line)
        cell["source"] = new_source
    if changed:
        with open(nb_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)
        print(f"  Injected overdue_giveup_fac into {nb_path.name}")
    return changed


def run_notebook(nb_path):
    """Execute a notebook in place and clear output. Returns True on success."""
    print(f"\n{'='*60}")
    print(f"Running: {nb_path.relative_to(TUTORIALS.parent)}")
    print(f"{'='*60}")
    t0 = time.time()

    # Patch notebooks for testing, keeping a backup to restore after.
    # IES-specific (reduced realizations/iterations) is path-scoped; the panther
    # overdue_giveup_fac injection is content-scoped via uses_panther().
    backup = nb_path.read_bytes()
    if "part2_06_ies" in str(nb_path):
        patch_ies_notebook(nb_path)
    if "part1_13" in str(nb_path):
        patch_part1_ies_notebook(nb_path)
    if nb_path.name == "freyberg_glm_2.ipynb":
        patch_noptmax(nb_path, 1)
    if nb_path.name in ("freyberg_sqp_1.ipynb", "freyberg_sqp_2.ipynb"):
        # pestpp-sqp runs are slow on the Windows/macOS runners; 20 iterations
        # overran the 1800s per-cell timeout, so cap at 3 for CI.
        patch_noptmax(nb_path, 3)
    patch_overdue_giveup_fac(nb_path)

    result = subprocess.run(
        [
            sys.executable, "-m", "jupyter", "nbconvert",
            "--execute",
            f"--ExecutePreprocessor.timeout={TIMEOUT}",
            "--inplace",
            str(nb_path),
        ],
        cwd=str(nb_path.parent),
        capture_output=False,
    )

    elapsed = time.time() - t0
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"{status}: {nb_path.name} ({elapsed:.0f}s)")

    # Restore original notebook content (reverts any patching above)
    nb_path.write_bytes(backup)

    # Clear output and metadata regardless of success
    subprocess.run(
        [
            sys.executable, "-m", "jupyter", "nbconvert",
            "--ClearOutputPreprocessor.enabled=True",
            "--ClearMetadataPreprocessor.enabled=True",
            "--inplace",
            str(nb_path),
        ],
        cwd=str(nb_path.parent),
        capture_output=True,
    )

    return result.returncode == 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_notebooks.py <prefix> [<prefix> ...]")
        print("  e.g.: python run_notebooks.py part0")
        print("  e.g.: python run_notebooks.py part2_01 part2_02")
        sys.exit(1)

    prefixes = sys.argv[1:]
    failures = []
    total = 0

    for prefix in prefixes:
        # If a broad prefix like "part1", sort sections in defined order
        if prefix == "part1":
            all_sections = []
            for p in PART1_ORDER:
                all_sections.extend(get_sections(p))
        else:
            all_sections = get_sections(prefix)

        if not all_sections:
            print(f"WARNING: no sections found matching '{prefix}'")
            continue

        for section in all_sections:
            notebooks = get_notebooks(section)
            for nb in notebooks:
                total += 1
                if not run_notebook(nb):
                    failures.append(str(nb.relative_to(TUTORIALS.parent)))

    print(f"\n{'='*60}")
    print(f"Results: {total - len(failures)}/{total} passed")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All notebooks passed!")


if __name__ == "__main__":
    main()
