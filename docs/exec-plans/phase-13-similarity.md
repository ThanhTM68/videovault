# Phase 13 — V2 Similarity & Quality Analysis

## Goal
Group likely duplicate/reuploaded media and compare quality without claiming provenance as fact.

## Model
gpt-6.1-sol high.

## Iterative implementation
1. exact SHA-256
2. perceptual keyframe hash
3. basic text/title similarity
4. optional audio/transcript/embedding later

## Quality metrics
- resolution
- bitrate
- fps
- sharpness proxy
- compression indicators

Use labels:
- likely similar
- possible reupload
- earliest known version
- higher-quality candidate

Do not assert "original source" without evidence.
