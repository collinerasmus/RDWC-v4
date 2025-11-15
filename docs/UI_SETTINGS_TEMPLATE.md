# UI Settings Section Template

**Canonical source:** EC tab in `app/static/index.html` (as of version 20251115o)

## Pattern Overview

All settings collapsible sections should follow this structure for visual consistency:

### 1. Container
```html
<details style="margin-top:12px;">
  <summary class="muted" style="cursor:pointer;font-size:0.9rem;">Section Name</summary>
  <div style="margin-top:12px;padding:12px;border-radius:8px;background:rgba(59,130,246,0.05);border:1px solid rgba(59,130,246,0.2);">
    <!-- Content -->
  </div>
</details>
```

### 2. Description (optional)
```html
<div class="muted" style="font-size:0.75rem;margin-bottom:8px;">
  Brief description of the section purpose.
</div>
```

### 3. Status Chips (if applicable)
```html
<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center;">
  <span class="pill-muted nowrap" id="someChip">Status</span>
</div>
```

### 4. Sub-sections
Each logical grouping:
```html
<div style="margin-bottom:12px;">
  <div style="font-weight:600;margin-bottom:6px;font-size:0.85rem;color:#e0e0e0;">Sub-section Title</div>
  <div class="muted" style="font-size:0.7rem;margin-bottom:6px;">Optional sub-description</div>
  <!-- Input grid -->
</div>
```

### 5. Input Grids
**Spacing rules:**
- Grid gap: `8px`
- Row margin-bottom: `6px` (except last row)
- Section margin-bottom: `12px`

**Two-column layout:**
```html
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
  <div>
    <label style="display:block;font-size:0.75rem;margin-bottom:2px;color:#9ca3af;">Label</label>
    <input type="number" id="fieldId" style="width:100%;padding:4px 2px;background:transparent;border:none;border-bottom:1px solid rgba(148,163,184,0.3);color:#e0e0e0;border-radius:0;font-size:0.85rem;" />
  </div>
</div>
```

**Three-column layout:**
```html
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
  <!-- Same label/input pattern -->
</div>
```

### 6. Save Button
```html
<button id="btnSaveSettings" class="btn-secondary" style="width:100%;">Save Settings</button>
```

## Key Measurements

| Element | Value | Purpose |
|---------|-------|---------|
| Details margin-top | 12px | Consistent spacing between collapsible sections |
| Content padding | 12px | Breathing room inside card |
| Border radius | 8px | Soft corners matching theme |
| Background | rgba(59,130,246,0.05) | Subtle blue tint |
| Border | 1px solid rgba(59,130,246,0.2) | Gentle edge definition |
| Grid gap | 8px | Tight but readable field spacing |
| Section margin-bottom | 12px | Logical grouping separation |
| Label font-size | 0.75rem | Compact, readable |
| Label margin-bottom | 2px | Minimal label-to-input gap |
| Heading font-size | 0.85rem | Sub-section titles |
| Description font-size | 0.7rem | Small helper text |

## Input Style (Underline Pattern)
```css
width:100%;
padding:4px 2px;
background:transparent;
border:none;
border-bottom:1px solid rgba(148,163,184,0.3);
color:#e0e0e0;
border-radius:0;
font-size:0.85rem;
```

## Rollout Checklist

When applying this template to other tabs:

1. **Preserve all IDs** — do not change element IDs; JS depends on them
2. **Match heading structure** — use consistent sub-section titles
3. **Maintain grid layouts** — 1fr 1fr for pairs, 1fr 1fr 1fr for triplets
4. **Keep spacing uniform** — 8px gaps, 12px section margins, 6px row margins
5. **Test interaction** — ensure save buttons and field updates work post-change
6. **Bump cache-buster** — increment `meta[name="version"]` and deploy

## Current Status

✅ **EC tab** — Parameters, Manual Dosing (Volume), Pump Control (Time), Dose Log (Last 20)  
⏳ **Pending** — pH, Sensors, Chiller/Temp, Circulation, Lights, Scheduler

---

**Last updated:** 2025-11-15 (version 20251115o)
