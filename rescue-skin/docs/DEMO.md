# RESCUE SKIN — Competition Demo Guide

**VK26-IITH-SC-0046** · Sustainable Cities · Stage 2 prototype

## Running the demo

1. Start the backend:

   ```
   cd rescue-skin
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

2. Open `http://127.0.0.1:8000` in a browser (the dashboard).
3. Click **START COMPETITION DEMO**.
4. Use **Pause** / **Resume** to step through with an audience.
5. Watch the **Event Log**, **Live Route**, **Map**, and **Communication topology**
   panels.
6. Click **Reset** to return to a clean normal state.

## Demo sequence

| Step | What happens | What to show |
|------|--------------|--------------|
| 1 | Normal building | All zones NORMAL, route via Exit A |
| 2 | Three occupants present | Occupancy rises in Zone C |
| 3 | Simulated hazard | Temperature injected in Zone C |
| 4 | Abnormal readings detected | Zone C moves to WATCH / RESTRICTED |
| 5 | Zone restricted | Zone C highlighted red, removed from routing |
| 6 | Exit A unavailable | Exit A blocked |
| 7 | Automatic reroute to Exit B | Route recalculates, path animates to Exit B |
| 8 | Link failure | One comms link drops, downstream zones uncertain, local operation continues |
| 9 | Accessibility route | ACCESSIBLE profile: ramp used, stairs avoided |
| 10 | Recovery | Link restored, hazards cleared, route returns to Exit A |

## Accessibility scenario

Select **ACCESSIBLE (wheelchair)** in the routing-profile control. The route
recalculates using ramps and accessible corridors and avoids stairs. This is an
operator-selected assistance requirement only — the system never assumes a
person's identity.

## Communication-failure demo

Click **Link fail: N01-N02**. Nodes downstream of the broken link go offline,
their zones turn uncertain/stale, and the event log shows `LINK_FAILURE`. The
rest of the building keeps operating and the route adapts. Click **Restore all**
to recover.

## What the audience should see

- Map zones changing colour (green → amber → red → grey)
- Route line redrawing and the head marker animating along the new path
- Previous / new route and the "why the route changed" explanation
- LED / AUDIO / HAPTIC guidance simulation text (no real hardware)
- Event log timestamps
- Targets vs measured performance panel (targets live; measurements marked
  `NOT YET MEASURED` until taken)

## Disclaimer (shown on dashboard)

> RESCUE SKIN is a student research prototype demonstrated using controlled,
> non-hazardous simulations. It is not a certified life-safety system.
