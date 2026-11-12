# Bite 2: Store (I2) [WHAT DOES THIS DO ?? I DONT EVEN UNDERSTAND THE POINT OF THIS PLAN, HOW AM I SUPPOSED TO SAY ANYTHING OR CONTRIBUTE HERE ? ] 

## For you

**What already exists.** There's no shared database yet. `Database/sqlite/` holds five separate SQLite files, each made by a different older system (the gateway's cost ledger, audit, pairings, a cache). The old learning system's `mvp_store.py` (641 lines, in `workshop/Original Code/`) has connection settings worth copying. The rest of it is that system's own tables. There's no `core/` folder and no root project setup.

**What's being built.** `core/store.py`, about 80 lines. It opens one shared database file and lets each component add its own tables in numbered steps, each applied exactly once. That way, ten agents don't end up with ten databases. This bite also adds the root project setup (`pyproject.toml` and a lock file) that bites 3 and 4 need.

**Your input** (write under each one):

1. Build this now, or move it to Stage 1, when the CFA loop needs its first table? My recommendation: move it.
   - Your answer:
2. Is `Database/sqlite/aios.sqlite` fine as the shared file's location?
   - Your answer:

---

**Goal:** one SQLite file where each owner applies its own numbered table changes exactly once (see `nodes/eventlog.md`).
**Builder:** Claude. **After:** nothing. It can run alongside bite 1. **Budget:** about 80 lines.

**Set up** `core/` **(the first core bite does this):**

- Add a root `pyproject.toml` and a uv lock file. A lock file records exact library versions.
- Build the environment with `uv sync --python 3.11.15`.
- Add Pydantic, which is already approved. Record it in `DEPENDENCIES.md`.

**Write the tests first:** `tests/contracts/test_i2.py`, all on a temporary file.

- Two owners (`alpha`, `beta`) each migrate two steps into one fresh file, and both sets of tables exist.
- Running both again changes nothing, and the `migrations` table still has four rows.
- A new step 3 for `alpha` applies only step 3.
- WAL mode and foreign keys are on.
- With no `AIOS_DB` set, the path is `Database/sqlite/aios.sqlite`. Assumed.

**Build:** `core/store.py` with `connect()` and `migrate(conn, owner, steps)`. The `migrations` table records owner, step and date. From the old `mvp_store.py`, take only the connection settings.

**Done when:** `pytest tests/contracts/test_i2.py` passes.
**Out of scope:** the events table and Litestream (Stage 3), and any real node's tables.
