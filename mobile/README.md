# SESIS-FEDERATION — Mobile COP App

> **Offline-first Common Operating Picture for tactical field operators**
>
> Built with Flutter — mesh networking, ghost mode, end-to-end encryption.

## Architecture

```
sesis_cop/
├── lib/
│   ├── main.dart                 # App entry point
│   ├── core/
│   │   ├── constants.dart        # App-wide constants
│   │   ├── theme/
│   │   │   ├── app_theme.dart    # Military dark theme
│   │   │   └── colors.dart       # Color palette
│   │   ├── network/
│   │   │   ├── api_client.dart   # HTTP client with cert pinning
│   │   │   ├── mesh_service.dart # P2P mesh networking
│   │   │   └── mesh_protocol.dart# Mesh message protocol
│   │   ├── security/
│   │   │   ├── crypto_service.dart # AES-256-GCM + Kyber768
│   │   │   └── auth_service.dart   # JWT + MFA
│   │   └── storage/
│   │       ├── local_db.dart     # SQLite offline database
│   │       ├── sync_service.dart # Background online sync
│   │       └── offline_queue.dart# Priority offline queue
│   └── features/
│       ├── dashboard/            # Main COP screen with map
│       ├── intel/                # Intelligence feed
│       ├── c2/                   # Command & Control
│       ├── agents/               # Field agent management
│       ├── satellite/            # Satellite imagery viewer
│       ├── auth/                 # Login, MFA, duress
│       └── ghost/                # Ghost mode & coercion
└── pubspec.yaml
```

## Build Instructions

### Prerequisites
- Flutter SDK >= 3.0.0
- Dart SDK >= 3.0.0
- Android Studio / Xcode
- A Google Maps API key (for satellite layer)

### Setup

```bash
cd mobile/sesis_cop
flutter pub get
flutter run
```

### Build for Android
```bash
flutter build apk --release
```

### Build for iOS
```bash
flutter build ios --release
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Offline-first** | Full local SQLite DB, mesh relay, store-and-forward |
| **Mesh Networking** | P2P via Nearby Connections, epidemic routing |
| **Ghost Mode** | Decoy UI, duress PIN, silent emergency alerts |
| **E2E Encryption** | AES-256-GCM + Kyber768 post-quantum stubs |
| **Tactical Map** | Flutter map with unit positions, overlays, icons |
| **Intel Feed** | Real-time multi-INT fusion display |
| **C2 Alerts** | Mission timeline, alert prioritization |
| **Classification** | Multi-level badge display (STANAG 4774) |

## Security
- All data encrypted at rest (flutter_secure_storage + SQLite cipher)
- Certificate pinning for all HTTP connections
- Duress PIN triggers silent alert + fake UI
- Ghost mode disables all network indicators
- Authentication: JWT short-lived tokens + MFA (TOTP)
