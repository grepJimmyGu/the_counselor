---
name: safe-migration
description: Reviews Alembic database migrations for safety issues, conflicts, and production risks before committing. Use when creating or modifying Alembic migrations, or before creating PR with database changes. Checks for multiple heads, merge migrations, and dangerous operations.
---

# Safe Migration Skill

## Overview

This skill provides systematic safety review for Alembic database migrations before they reach production. Database migrations in this project are automatically applied when code reaches the main branch, making pre-deployment validation critical.

**Why this matters:**
- Migrations auto-apply on production deployment from main
- Unsafe operations can lock tables and cause downtime
- Migration conflicts break deployments
- Data loss from DROP operations is irreversible
- Performance issues affect production immediately

---

## Critical Safety Checks

### 1. Multiple Heads (CRITICAL - Blocks Deployment)
**What**: Multiple migration branches exist
**Detection**: Run alembic heads - output should show single revision
**Fix**: Linearize the chain (see Resolving Multiple Heads below)
**Why critical**: Deployment fails if migration graph has multiple endpoints

### 2. Branch Migration Drift (CRITICAL)
**What**: PR branch has modified migrations that exist on main (corrupted during merge)
**Detection**: git diff origin/main -- alembic/versions/
**Fix**: Reset drifted files with git checkout origin/main -- file
**Why critical**: Modifying mains migrations breaks the chain and causes double heads

### 3. Irreversible Operations (Data Loss Risk)
**What**: Operations that destroy data without recovery path
**Detection**: Look for drop_table, drop_column, drop_constraint
**Fix**: Stage removal (remove code usage first, drop in next release), test downgrade

### 4. Table Locks (Downtime Risk)
**What**: Operations that lock tables during migration
**Detection**: add_column NOT NULL, create_index, alter_column type changes
**Fix**: Add nullable columns first, backfill, then add constraint

### 5. Data Migrations (Reliability Risk)
**What**: Data transformations within migrations
**Detection**: execute(), op.bulk_insert(), connection operations
**Fix**: Make idempotent, batch large operations, test downgrade thoroughly

### 6. Merge Migrations (FORBIDDEN)
**What**: Migration with tuple down_revision merging two branches
**Detection**: down_revision is a tuple instead of string
**Fix**: NEVER use alembic merge - linearize instead (see below)
**Why critical**: Causes skipped migrations and impossible downgrades

---

## Resolving Multiple Heads

**NEVER use alembic merge** - it creates tuple down_revision causing:
- Skipped migrations in production
- Missing database tables
- Impossible downgrade paths

### Correct Approach: Linearize the Chain

1. **Check for migration drift first**:
   Run: git diff origin/main -- alembic/versions/
   If any migrations from main were modified, reset them:
   Run: git checkout origin/main -- alembic/versions/modified_file.py

2. **Identify the current head on main** by tracing down_revision values

3. **Update your migrations down_revision** to point to mains head

4. **Verify single head**: alembic heads should show ONE revision

---

## Workflow

### 1. Check for Migration Drift (CRITICAL - Do First)
Before any other checks, compare branch migrations against main:
Run: git diff origin/main -- alembic/versions/
- If existing migrations were modified: Reset them from main
- Only NEW migration files should differ

### 2. Run Safety Checks
- Check for multiple heads: alembic heads
- Check for tuple down_revision (merge migrations)
- Review for dangerous operations

### 3. Test Migration Locally
- Upgrade: alembic upgrade head
- Downgrade: alembic downgrade -1
- Upgrade again to confirm reversibility

### 4. Generate Safety Report
- Passed: Checks that passed
- Warnings: Non-blocking concerns
- Issues: Blocking problems

---

## Common Mistakes

### Using alembic merge for Multiple Heads
**Problem**: Creates tuple down_revision, breaks production
**Fix**: Linearize the chain - each migration has exactly ONE string parent

### Modifying Existing Migrations During Merge Conflicts
**Problem**: Merge conflicts in migration files get resolved by changing down_revision
**Fix**: Always reset migrations from main, only modify YOUR new migration
**Detection**: git diff origin/main shows changes to mains migrations

### Not Checking Migration Drift Before Fixing Heads
**Problem**: Fix your migrations parent but branch has corrupted mains migrations
**Fix**: ALWAYS check git diff origin/main first, reset drifted files
**Detection**: Multiple heads persist after fixing your migrations down_revision

### Not Testing Downgrade
**Problem**: Migration works forward but fails backward
**Fix**: Always test alembic downgrade -1 before committing

### Adding NOT NULL Without Default
**Problem**: Locks table, fails on existing rows
**Fix**: Add as nullable first, backfill data, then add constraint

### Dropping Columns Without Staging
**Problem**: Code still references column, causes errors
**Fix**: Remove code references in PR 1, drop column in PR 2

---

## Red Flags (Fail Fast)

- Multiple heads detected
- down_revision is a tuple (merge migration)
- PR modifies migrations that exist on main
- drop_table or drop_column without staged removal
- add_column NOT NULL without default value
- Downgrade not tested or fails
- Data migration without idempotency
