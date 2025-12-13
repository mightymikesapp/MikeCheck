# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-12-13

### Features
- **Deep Shepardizing**: Implemented recursive negative treatment propagation to better analyze case validity depth.
- **Frontend**: Added a complete React-based frontend application (`frontend/`) featuring:
  - Dashboard, Document Review, and Citation Network pages.
  - Shadcn/UI component library integration.
  - Visualization components (Map, Citation Graph).
- **Kubernetes**: Added comprehensive Kubernetes deployment manifests (`k8s/`) including Deployment, Service, HPA, and ServiceMonitor.
- **Testing**: Added a massive suite of tests (`tests/`) covering unit, integration, and benchmarks for the analysis layer.

### Chore
- **Infrastructure**: Updated project configuration (`pyproject.toml`) and added lock files (`uv.lock`, `pnpm-lock.yaml`).
- **Typing**: Enhanced type safety in the analysis layer.
