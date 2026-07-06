# 3D Room Capture — Platform-Agnostic Implementation Guide

A high-level reference for implementing on-device 3D room capture in a way
that stays portable across app shells (native, Capacitor, React Native),
backends (AWS, other clouds, self-hosted), and databases. The goal: swap
any one layer without rewriting the others.

## Core principle

Treat this as four independent layers connected by plain data contracts,
not framework APIs. As long as each layer's *output* matches an agreed
schema, the implementation behind it is replaceable.

```
[1] Capture  →  [2] Interchange format  →  [3] Local storage  →  [4] Backend sync
```

---

## 1. Capture layer

**What it does:** Uses the device's AR/LiDAR framework to scan a room and
detect walls, doors, windows, and openings with real-world dimensions.

**Platform reality (unavoidable, not agnostic):**
- iOS: Apple's RoomPlan framework (LiDAR-equipped iPhones/iPads, 12 Pro+)
- Android: no direct equivalent yet; ARCore provides raw plane detection
  but not structured room semantics — expect to build more of the
  wall/door/window classification yourself, or rely on manual polygon
  tracing as a fallback
- This layer is inherently platform-native code (Swift/Kotlin), regardless
  of what wraps it (see Section 4)

**Agnostic design choice:** keep capture code isolated behind a single
function boundary — e.g. `startCapture() -> RoomCaptureResult` — so the
app shell calling it doesn't need to know whether that's a native
ViewController, a Capacitor plugin bridge, or a React Native native module.

## 2. Interchange format

**What it does:** Converts the platform's proprietary capture result
(e.g. Apple's `CapturedRoom` object) into a plain, versioned JSON schema
that has no dependency on any SDK.

**Why this matters most:** This is the layer that actually makes the
whole system agnostic. Everything downstream — local storage, sync,
compliance processing, CAD import — should only ever read this schema,
never the native capture object directly.

Minimal schema shape:

```json
{
  "schema_version": "1.0",
  "room_label": "kitchen",
  "captured_at": "2026-07-06T10:00:00Z",
  "units": "meters",
  "surfaces": [
    {
      "category": "wall",
      "position": { "x": 0.0, "y": 0.0, "z": 0.0 },
      "dimensions": { "width": 3.2, "height": 2.4, "depth": 0.1 },
      "transform_matrix": [ /* 16 values, row-major */ ]
    }
  ]
}
```

Keep it flat, versioned (`schema_version`), and free of vendor-specific
types (no `simd_float4x4`, no platform structs — plain numbers and
strings only).

## 3. Local storage

**What it does:** Persists captured scans on-device between sessions and
before/instead of syncing anywhere.

**Agnostic options, roughly in order of portability:**
- Embedded SQL (SQLite, via whatever binding your app shell offers) —
  most portable, works identically regardless of app shell choice
- Structured file storage (one JSON file per scan) — simplest, fine for
  low scan volumes, easy to inspect/debug/back up manually
- Platform-native stores (Core Data, Room/Android) — least portable, ties
  you to one platform's persistence framework

**Recommendation:** SQLite (or a thin file-based store) over
platform-native persistence, specifically because it keeps this layer
swappable if you change app shells later.

## 4. App shell (the replaceable wrapper)

This is the layer most people over-couple to. The capture and interchange
layers above don't care which of these you pick:

| Shell | Capture integration | Tradeoff |
|---|---|---|
| Native (Swift/SwiftUI, Kotlin) | Direct, first-party | Most control, least code reuse across platforms |
| Capacitor / hybrid web | Custom native plugin bridges capture into JS | Reuses existing web frontend, adds a bridge layer |
| React Native | Custom native module, same bridging idea | Similar tradeoff to Capacitor |

Whichever you choose, the shell's only job is: call capture, receive the
interchange-format JSON, hand it to local storage. It should not contain
any capture logic itself.

## 5. Backend sync (optional, and minimal by design)

**What it does:** Sends only what a server-side process actually needs —
not the raw scan.

**Agnostic pattern:**
- Compute derived values on-device (footprint polygon, total area, wall
  lengths) from the interchange-format data
- Send only that derived summary plus whatever reference ID the backend
  needs (e.g. property ID) — never the full geometry, unless the backend
  genuinely needs to reconstruct full 3D geometry
- Backend choice (AWS Lambda, another cloud, self-hosted) is irrelevant
  to this contract — it's just "send small JSON, get small JSON back"

**Privacy note:** this pattern keeps raw spatial data (a literal map of
someone's home) on the device by default. Treat "does this need to leave
the device at all" as the first question for every new field you're
tempted to sync, not an afterthought.

## 6. Export for external tools (CAD, visualization)

Because the interchange format (Section 2) is plain JSON with position/
dimension/transform data, any tool that can parse JSON can consume it —
FreeCAD via a Python macro, Blender via a Python script, a custom DXF
writer, etc. This is also where a secondary export like `.usdz` or
`.gltf` is useful for visual/AR use cases, kept separate from the
structured data used for measurement and compliance logic.

---

## Checklist for staying agnostic

- [ ] Capture code lives behind one function boundary, isolated from the app shell
- [ ] A versioned, vendor-free JSON schema is the *only* thing other layers read
- [ ] Local storage uses an embedded format (SQLite/JSON files), not a platform-locked ORM
- [ ] Backend payloads carry derived summaries, not raw scans, by default
- [ ] Any platform-specific type (native structs, SDK objects) is converted to plain data before it crosses a layer boundary
