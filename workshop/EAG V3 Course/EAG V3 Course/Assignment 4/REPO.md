# Where this folder is pushed

This folder goes to two places.

**1. Its own private repo:** https://github.com/Aryamanchandak/eag-v3-assignment-04
The history for that repo lives in the hidden folder `.git-standalone/` here.

**2. The AI OS repo**, as part of normal commits made from the AI OS root.

## Push this folder to the assignment repo

Run these inside this folder.

```bash
git --git-dir=.git-standalone --work-tree=. add -A
```
Stages every change in this folder.

```bash
git --git-dir=.git-standalone --work-tree=. commit -m "say what changed"
```
Saves the staged changes as one commit.

```bash
git --git-dir=.git-standalone --work-tree=. push
```
Sends the commits to GitHub.

## Work on a separate copy

```bash
git clone git@github.com:Aryamanchandak/eag-v3-assignment-04.git
```
That copy is a normal repo: plain `git add`, `git commit`, `git push` work there.

## Delink

Delete `.git-standalone/` and this file. The GitHub repo and the AI OS copy are untouched.
