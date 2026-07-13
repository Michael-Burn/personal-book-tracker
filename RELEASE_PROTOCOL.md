# RELEASE_PROTOCOL.md

# Kwalitec Library Release Protocol

**Document Version:** 1.0  
**Applies From:** Version 1.1 onwards  
**Status:** Official Release Process

---

# 1. Purpose

This document defines the official release process for **Kwalitec Library**.

Its objectives are to:

- Protect production data
- Ensure every deployment is repeatable
- Prevent accidental releases
- Maintain a clean Git history
- Provide reliable rollback points
- Keep production stable
- Preserve the long-term quality of the application

Kwalitec Library is a production application.

Every release should follow this protocol.

---

# 2. Product Philosophy

Kwalitec Library is a **Reading Journal**.

Its purpose is to help readers:

- record
- preserve
- understand
- analyse
- celebrate

their reading journey.

It is **not** intended to become:

- Goodreads
- Kindle
- Apple Books
- an online e-reader

Every feature must strengthen the reading journey.

If a feature makes the application more complicated without improving that purpose, it should be rejected or postponed.

---

# 3. Release Principles

Every release must be:

- Stable
- Predictable
- Backwards compatible where practical
- Production-safe
- Data-safe

Production user data is the highest priority.

No release should ever place existing user libraries at risk.

---

# 4. Branch Strategy

The repository uses two permanent branches.

```
develop
    │
    │ Development
    ▼
prepare-render
    │
    │ Production Release
    ▼
Render
```

---

## develop

Used for:

- Feature development
- Bug fixes
- UI improvements
- Refactoring
- Experiments

Never deploy directly from this branch.

---

## prepare-render

Represents production-ready code.

Only tested code should exist here.

Render deploys directly from this branch.

---

# 5. Versioning Strategy

Semantic Versioning is used.

---

## Patch Release

Examples

```
1.0.1

1.0.2
```

Use for:

- Bug fixes
- UI polish
- Accessibility improvements
- Performance improvements
- Security fixes

---

## Minor Release

Examples

```
1.1.0

1.2.0
```

Use for:

- New user-facing functionality
- Theme improvements
- Export functionality
- Dashboard enhancements
- Reading analytics

Backward compatible.

---

## Major Release

Examples

```
2.0.0
```

Use for:

- Large redesign
- Architecture changes
- Breaking changes

---

# 6. Feature Acceptance Gate

Before implementing any feature ask:

Does this feature improve the reader's ability to:

- record reading?
- preserve reading history?
- reflect on reading?
- understand reading habits?
- share reading achievements?

If the answer is **No**, the feature should be reconsidered.

Avoid feature creep.

Maintain product focus.

---

# 7. Definition of Done

A release is not complete until ALL of the following are true.

---

## Functionality

- No Internal Server Errors
- No broken routes
- No failing forms
- Uploads work
- Charts work
- Theme switching works
- Smart Book Entry works
- Reading Year works

---

## User Interface

- Responsive
- Consistent spacing
- Consistent typography
- Consistent colours
- No layout overflow
- No broken hover states
- No clipped text
- No duplicate actions

---

## Performance

- Images lazy loaded
- Page-specific JavaScript only
- No unnecessary rendering
- Smooth scrolling
- Responsive interactions

---

## Accessibility

- Keyboard navigation
- Focus states
- Colour contrast
- Screen-reader friendly labels

---

## Database

- Migration reviewed
- Migration tested locally
- Existing production data preserved
- No destructive migrations

---

# 8. Database Safety Rules

Always:

- Create additive migrations
- Test migrations locally
- Preserve existing production data
- Preserve uploads
- Preserve avatars
- Preserve covers

Never:

- Drop production tables
- Delete production data
- Rewrite user history
- Modify user records unnecessarily

---

# 9. Local Release Procedure

## Step 1

Activate virtual environment.

```bash
source .venv/bin/activate
```

---

## Step 2

Switch to development branch.

```bash
git checkout develop
```

---

## Step 3

Review changes.

```bash
git status
```

---

## Step 4

Stage changes.

```bash
git add .
```

---

## Step 5

Verify staged files.

```bash
git status
```

---

## Step 6

Commit.

Example:

```bash
git commit -m "Improve reading journal experience"
```

---

## Step 7

Push develop.

```bash
git push origin develop
```

---

## Step 8

Switch to production branch.

```bash
git checkout prepare-render
```

---

## Step 9

Merge.

```bash
git merge develop
```

Resolve conflicts if necessary.

---

## Step 10

Push production branch.

```bash
git push origin prepare-render
```

Render deploys from this branch.

---

## Step 11

Run migrations locally.

```bash
flask db upgrade
```

---

## Step 12

Verify migration.

```bash
flask db current
```

Should display:

```
(head)
```

---

# 10. Production Deployment

If automatic deployment does not begin:

Render

↓

Manual Deploy

↓

Deploy Latest Commit

Monitor deployment logs.

Deployment is only considered complete after:

- Build succeeds
- Dependencies install
- Migrations complete
- Gunicorn starts
- No tracebacks appear

---

# 11. Production Smoke Test

---

## Authentication

- Login
- Logout
- Register
- Settings

---

## Home

- Dashboard loads
- Theme switching
- Quote rotation
- Reading Goal
- Snapshot
- Quick Actions

---

## Authors

- Search
- Filters
- Author detail

---

## Library

- Book cards
- Grid/List
- Filters

---

## Books

- Add
- Edit
- Delete
- Smart Entry
- Covers
- Timeline

---

## Quotes

- Add Quote
- Edit Quote
- Favourite Quote
- Share

---

## Reading

- Reading Goal
- Reading Year
- Analytics

---

## Admin

- Users
- Library
- Authors
- Analytics

---

## Media

- Avatar upload
- Cover upload

---

# 12. Release Tags

Official releases must be tagged.

Example:

```bash
git tag -a v1.2.0 -m "Kwalitec Library Version 1.2.0"
```

Push:

```bash
git push origin v1.2.0
```

Never modify an existing release tag.

---

# 13. GitHub Release

Every official release should include:

- Version
- Summary
- New Features
- Improvements
- Bug Fixes
- Screenshots (where appropriate)

---

# 14. Rollback Procedure

If production deployment fails:

1. Restore previous Render deployment.

2. Restore previous Git tag.

3. Restore database backup ONLY if production data has become corrupted.

Never restore production data simply because a deployment failed.

---

# 15. Release Checklist

Before every release verify:

## Code

- Clean commit history
- No debugging code
- No dead CSS
- No unused templates

---

## Database

- Migration verified
- Backup available
- Production-safe

---

## User Experience

- Responsive
- Theme consistent
- Interaction consistent
- Reading Journal philosophy maintained

---

## Performance

- No excessive JavaScript
- No unnecessary database queries
- Lazy loading working

---

## Accessibility

- Keyboard navigation
- Focus states
- Contrast

---

## Production

- Render deploy successful
- Smoke test complete
- No server errors

---

## Git

- develop pushed
- prepare-render merged
- prepare-render pushed
- Release tag created
- GitHub Release published

---

# 16. Maintenance Policy

Version 1.x should focus on:

- Bug fixes
- UI polish
- Accessibility
- Performance
- Security
- Stability

Avoid adding major new functionality unless it clearly strengthens the product philosophy.

---

# 17. Long-Term Vision

Kwalitec Library exists to preserve a reader's journey.

Every release should make the application:

- easier to use
- more reliable
- more beautiful
- more consistent
- more enjoyable

without sacrificing simplicity.

When faced with two design options:

Choose:

- clarity over decoration
- consistency over novelty
- information over clutter
- speed over visual effects

The goal is to build a timeless Reading Journal that readers enjoy returning to for many years.
