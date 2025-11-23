# RDWC v4 UI Template Benchmark

**Document**: UI-BENCHMARK-001  
**Project**: RDWC v4 User Interface Standardization  
**Revision**: v1.0 (Phase 8 Lockdown)  
**Date**: 2025-11-23  

---

## Purpose

This document serves as the **definitive reference** for RDWC v4 UI design patterns established during Phase 8 standardization. All future UI changes MUST conform to these patterns to maintain visual consistency and user experience quality.

**Status**: ✅ **LOCKED** — No deviations permitted without formal design review.

---

## Table of Contents

1. [KPI Block Pattern](#kpi-block-pattern)
2. [Details Section Pattern](#details-section-pattern)
3. [System Card Pattern](#system-card-pattern)
4. [Color Palette](#color-palette)
5. [Typography System](#typography-system)
6. [Status Badges](#status-badges)
7. [Button Styles](#button-styles)
8. [Grid Layouts](#grid-layouts)
9. [Spacing & Rhythm](#spacing--rhythm)
10. [Examples by Tab](#examples-by-tab)

---

## 1. KPI Block Pattern

### 1.1 Standard KPI Block

**Purpose**: Display single metric with label and value  
**Usage**: ALL tabs for primary metrics (pH, EC, temp, CPU, etc.)

**HTML Structure**:
```html
<div class="kpi">
  <div class="kpi-label">Label Text</div>
  <div class="kpi-value">Value</div>
</div>
```

**CSS**:
```css
.kpi {
  background: var(--bg-pill);         /* #111827 */
  border: 1px solid var(--border-muted); /* rgba(148,163,184,0.15) */
  border-radius: 8px;
  padding: 10px 12px;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi-label {
  font-size: var(--font-xs);  /* 0.7rem */
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--fg-muted);  /* #9ca3af */
}

.kpi-value {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--fg-primary);  /* #e0e0e0 */
}
```

**Variants**:

- **Colored KPI** (Sensors tab):
  ```html
  <div class="kpi" style="background:rgba(59,130,246,0.08);border-color:rgba(59,130,246,0.25);">
    <div class="kpi-label">pH</div>
    <div class="kpi-value" style="color:#60a5fa;">6.0</div>
  </div>
  ```
  - **Blue**: pH, I²C devices → `rgba(59,130,246,...)`
  - **Green**: EC, GPIO pins → `rgba(34,197,94,...)`
  - **Orange**: Temp → `rgba(251,146,60,...)`
  - **Pink**: Sensor power → `rgba(236,72,153,...)`

- **Wide KPI** (System tab, longer text):
  ```html
  <div class="kpi" style="min-width:140px;">...</div>
  ```

- **Small Value KPI** (compact display):
  ```html
  <div class="kpi-value" style="font-size:var(--font-base);">...</div>
  ```

**Layout**: Always wrap in flex container with gap:
```html
<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
  <div class="kpi">...</div>
  <div class="kpi">...</div>
  <div class="kpi">...</div>
</div>
```

---

## 2. Details Section Pattern

### 2.1 Standard Details Container

**Purpose**: Group related settings/parameters in collapsible blue-tinted container  
**Usage**: pH Parameters, EC Parameters, Chiller Settings, Circulation Settings, Lights Settings, System Settings

**HTML Structure**:
```html
<details style="margin-top:12px;">
  <summary class="muted" style="cursor:pointer;font-size:var(--font-lg);">Section Title</summary>
  <div style="margin-top:12px;padding:6px;border-radius:8px;background:rgba(59,130,246,0.05);border:1px solid rgba(59,130,246,0.2);">
    <div class="muted" style="font-size:var(--font-sm);margin-bottom:12px;">
      Optional description text explaining section purpose.
    </div>
    <!-- 2-column grid layout -->
    <div style="display:grid;grid-template-columns:max-content max-content;column-gap:10px;row-gap:8px;align-items:center;">
      <label style="height:28px;width:120px;display:flex;align-items:center;">Param Name:</label>
      <input type="number" value="6.2" style="width:120px;height:28px;padding:0 6px;..." />
      <!-- Repeat for all parameters -->
    </div>
  </div>
</details>
```

**Key Properties**:
- **Container Background**: `rgba(59,130,246,0.05)` (blue tint)
- **Container Border**: `1px solid rgba(59,130,246,0.2)` (blue border)
- **Grid**: `grid-template-columns: max-content max-content` (2-column, auto-width)
- **Column Gap**: `10px` (space between label and input)
- **Row Gap**: `8px` (space between parameter rows)
- **Label Width**: `120px` (consistent across all sections)
- **Label Height**: `28px` (matches input height for alignment)
- **Input Width**: `120px` (consistent across all sections)
- **Input Height**: `28px` (consistent across all form controls)

**Applied To**:
- pH tab: "pH Parameters", "Auto Dosing", "Dose Safety Caps"
- EC tab: "EC Parameters", "Recipe", "Safety Caps"
- Chiller tab: "Chiller Settings"
- Circulation tab: "Circulation Settings"
- Lights tab: "Lights Settings"
- System tab: "General", "Safety", "Alerts", "UI" (4 sections)

**Example (pH Parameters)**:
```html
<details style="margin-top:12px;">
  <summary class="muted" style="cursor:pointer;font-size:var(--font-lg);">pH Parameters</summary>
  <div style="margin-top:12px;padding:6px;border-radius:8px;background:rgba(59,130,246,0.05);border:1px solid rgba(59,130,246,0.2);">
    <div class="muted" style="font-size:var(--font-sm);margin-bottom:12px;">
      Target pH range for auto-dosing. System doses pH UP when below pH Low.
    </div>
    <div style="display:grid;grid-template-columns:max-content max-content;column-gap:10px;row-gap:8px;align-items:center;">
      <label style="height:28px;width:120px;display:flex;align-items:center;">pH Low:</label>
      <input type="number" step="0.1" value="5.8" style="width:120px;height:28px;padding:0 6px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;" />
      
      <label style="height:28px;width:120px;display:flex;align-items:center;">pH High:</label>
      <input type="number" step="0.1" value="6.2" style="width:120px;height:28px;padding:0 6px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;" />
    </div>
  </div>
</details>
```

---

## 3. System Card Pattern

### 3.1 Standard System Card

**Purpose**: Group related system information (Pi, Software, Hardware, Database, Network, etc.)  
**Usage**: System tab ONLY

**HTML Structure**:
```html
<div class="system-card" style="margin-bottom:20px;">
  <div class="system-card-header">
    <span class="system-card-icon">🍓</span>
    <h4 class="system-card-title">Card Title</h4>
  </div>
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
    <!-- KPI blocks go here -->
  </div>
</div>
```

**CSS** (`theme_v4.css`):
```css
.system-card {
  padding: var(--space-lg);  /* 16px */
  background: var(--bg-card);  /* rgba(31,41,55,0.4) */
  border: 1px solid var(--border-normal);  /* rgba(55,65,81,0.5) */
  border-radius: var(--radius-lg);  /* 12px */
}

.system-card-header {
  display: flex;
  align-items: center;
  gap: var(--space-md);  /* 10px */
  margin-bottom: 14px;
}

.system-card-icon {
  font-size: 1.5rem;
}

.system-card-title {
  margin: 0;
  font-size: var(--font-xl);  /* 1.05rem */
  font-weight: 600;
}
```

**Example (Raspberry Pi Card)**:
```html
<div class="system-card" style="margin-bottom:20px;">
  <div class="system-card-header">
    <span class="system-card-icon">🍓</span>
    <h4 class="system-card-title">Raspberry Pi</h4>
  </div>
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
    <div class="kpi">
      <div class="kpi-label">CPU Usage</div>
      <div class="kpi-value">12.3%</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Memory Used</div>
      <div class="kpi-value">1.2 GB</div>
    </div>
    <!-- ... more KPIs -->
  </div>
</div>
```

**Icons**:
- 🍓 Raspberry Pi
- 💻 Software
- ⚙️ Hardware Environment
- 🗄️ Database
- 🌐 Network
- 📊 Processes
- 🔌 Relays
- 🏠 General Settings
- 🛡️ Safety Settings
- 🔔 Alerts Settings
- 🎨 UI Settings

---

## 4. Color Palette

### 4.1 Background Colors

```css
--bg-root: #0b0f14;           /* Page background (darkest) */
--bg-surface: #0d1117;        /* Unused (legacy) */
--bg-pill: #111827;           /* KPI blocks, buttons (dark gray) */
--bg-card: rgba(31,41,55,0.4); /* System cards (semi-transparent slate) */
--bg-card-elevated: rgba(31,41,55,0.6); /* Unused (legacy) */
```

### 4.2 Foreground Colors

```css
--fg-primary: #e0e0e0;  /* Primary text (light gray) */
--fg-muted: #9ca3af;    /* Muted text (gray-400) */
--fg-bright: #ffffff;   /* Bright text (rare use) */
```

### 4.3 Accent Colors

```css
--accent: #3b82f6;             /* Blue (primary actions, links) */
--accent-hover: #2563eb;       /* Blue hover (darker) */
--success: #10b981;            /* Green (online, success, OK) */
--warning: #f59e0b;            /* Orange (warning, check) */
--danger: #ef4444;             /* Red (error, offline, critical) */
```

### 4.4 Border Colors

```css
--border-muted: rgba(148,163,184,0.15);   /* Subtle borders */
--border-normal: rgba(55,65,81,0.5);      /* Normal borders */
--border-strong: rgba(148,163,184,0.25);  /* Strong borders */
```

### 4.5 Semantic Colors (Applied)

**Blue Tint** (pH, I²C, Details sections):
- Background: `rgba(59,130,246,0.05)` to `rgba(59,130,246,0.08)`
- Border: `rgba(59,130,246,0.15)` to `rgba(59,130,246,0.25)`
- Text: `#60a5fa` (blue-400)

**Green Tint** (EC, GPIO, Success):
- Background: `rgba(34,197,94,0.08)` to `rgba(34,197,94,0.15)`
- Border: `rgba(34,197,94,0.25)` to `rgba(34,197,94,0.45)`
- Text: `#22c55e` (green-500)

**Orange Tint** (Temperature, Warning):
- Background: `rgba(251,146,60,0.08)` to `rgba(251,146,60,0.15)`
- Border: `rgba(251,146,60,0.25)` to `rgba(251,146,60,0.35)`
- Text: `#fb923c` (orange-400)

**Pink Tint** (Sensor Power):
- Background: `rgba(236,72,153,0.08)`
- Border: `rgba(236,72,153,0.25)`
- Text: `#ec4899` (pink-500)

**Red Tint** (E-STOP, Danger):
- Background: `rgba(239,68,68,0.12)` to `rgba(239,68,68,0.85)` (active)
- Border: `rgba(239,68,68,0.45)` to `rgba(239,68,68,1)` (active)
- Text: `#fecaca` (red-200) to `#111827` (dark, on active)

---

## 5. Typography System

### 5.1 Font Sizes

```css
--font-xs: 0.7rem;    /* 11.2px - Small labels, captions */
--font-sm: 0.75rem;   /* 12px - Buttons, badges */
--font-base: 0.8rem;  /* 12.8px - Body text (reduced from 1rem) */
--font-md: 0.85rem;   /* 13.6px - Input text, summaries */
--font-lg: 0.95rem;   /* 15.2px - Section headers, KPI values */
--font-xl: 1.05rem;   /* 16.8px - Card titles */
--font-heading: 1.15rem; /* 18.4px - Page titles */
```

**Usage Guidelines**:
- **KPI Label**: `font-xs` (uppercase, letter-spacing 0.05em)
- **KPI Value**: `0.95rem` (font-lg, weight 600)
- **Button Text**: `font-sm` (weight 600)
- **Input Text**: `font-md`
- **Summary/Section Header**: `font-lg`
- **System Card Title**: `font-xl` (weight 600)
- **Page Title**: `font-heading` (H3, gradient effect)

### 5.2 Font Families

```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

**Monospace** (system info values):
```css
font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
```

### 5.3 Font Weights

- **400** (normal): Body text (rare, most text is 600)
- **500**: Sensor names, labels
- **600**: KPI values, buttons, section headers (PRIMARY weight)
- **700**: Dose buttons, pH/EC metrics
- **800**: E-STOP button

---

## 6. Status Badges

### 6.1 UI Status Chip

**Purpose**: Live indicators, health status, mode display  
**Usage**: Tab headers, controller status

**HTML Structure**:
```html
<span class="ui-status-chip success">Online</span>
```

**CSS**:
```css
.ui-status-chip {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
  border: 1px solid;
}

.ui-status-chip.success {
  background: rgba(34,197,94,0.1);
  color: #22c55e;
  border-color: rgba(34,197,94,0.3);
}

.ui-status-chip.neutral {
  background: rgba(148,163,184,0.1);
  color: #94a3b8;
  border-color: rgba(148,163,184,0.3);
}

.ui-status-chip.warning {
  background: rgba(251,146,60,0.1);
  color: #fb923c;
  border-color: rgba(251,146,60,0.3);
}

.ui-status-chip.danger, .ui-status-chip.error {
  background: rgba(239,68,68,0.1);
  color: #ef4444;
  border-color: rgba(239,68,68,0.3);
}
```

**Examples**:
- **success**: "Online", "Live", "OK", "Health Good"
- **neutral**: "Manual", "Standby", "OFF"
- **warning**: "Check", "Warning", "Low"
- **danger**: "Offline", "Error", "Critical"

---

## 7. Button Styles

### 7.1 Primary Button (btn-secondary)

**Purpose**: Main action buttons  
**Usage**: All tabs for primary actions

```css
.btn-secondary {
  padding: 6px 14px;
  background: #111827;
  color: #e0e0e0;
  border: 1px solid #1f2937;
  border-radius: 999px;  /* Pill shape */
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.25px;
  transition: background 0.15s ease, transform 0.12s ease;
}

.btn-secondary:hover {
  background: #1f2937;
}

.btn-secondary:active {
  transform: translateY(1px);
}
```

**Variants**:
```css
.btn-secondary.primary {  /* Blue accent */
  background: #2563eb;
  border-color: #3b82f6;
  color: #fff;
}

.btn-secondary.danger {  /* Red E-STOP style */
  background: rgba(239,68,68,0.15);
  color: #fecaca;
  border-color: rgba(239,68,68,0.45);
  font-weight: 700;
}

.btn-secondary.danger.active {  /* Active E-STOP */
  background: rgba(239,68,68,0.85);
  border-color: rgba(239,68,68,1);
  color: #111827;
}
```

**Size Modifiers**:
```css
.btn-small {
  padding: 4px 10px;
  height: 28px;
  font-size: var(--font-xs);
}

.btn-full {
  width: 100%;
}
```

### 7.2 Chip Button (btn-chip)

**Purpose**: Tab navigation, controller chips  
**Usage**: Top navigation, mode toggles

```css
.btn-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #111827;
  border: 1px solid #1f2937;
  color: #e0e0e0;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: var(--font-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-chip:hover {
  background: #1f2937;
}

.btn-chip.active {
  background: #2563eb;
  border-color: #3b82f6;
  color: #fff;
}
```

### 7.3 Relay Button (State-Dependent)

**Purpose**: Relay ON/OFF toggles  
**Usage**: System tab Relays section, controller-specific relay controls

```css
.relay-on {
  background: rgba(34,197,94,0.15);
  border: 1px solid rgba(34,197,94,0.45);
  color: #a7f3d0;
}

.relay-off {
  background: rgba(148,163,184,0.08);
  border: 1px solid rgba(148,163,184,0.25);
  color: #cbd5e1;
}
```

---

## 8. Grid Layouts

### 8.1 KPI Grid

**Purpose**: Horizontal arrangement of KPI blocks with wrapping

```html
<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
  <div class="kpi">...</div>
  <div class="kpi">...</div>
  <div class="kpi">...</div>
</div>
```

**Properties**:
- `display: flex` (not grid, for consistent wrapping)
- `align-items: center` (vertical centering)
- `gap: 12px` (standard spacing)
- `flex-wrap: wrap` (responsive wrapping)

### 8.2 Details Section Grid (2-Column)

**Purpose**: Label + input pairs in settings/parameters sections

```html
<div style="display:grid;grid-template-columns:max-content max-content;column-gap:10px;row-gap:8px;align-items:center;">
  <label style="height:28px;width:120px;">Label:</label>
  <input type="number" style="width:120px;height:28px;..." />
</div>
```

**Properties**:
- `grid-template-columns: max-content max-content` (auto-width columns)
- `column-gap: 10px` (space between label and input)
- `row-gap: 8px` (space between rows)
- `align-items: center` (vertical centering)
- **Label**: `width: 120px`, `height: 28px`
- **Input**: `width: 120px`, `height: 28px`

### 8.3 Relays Grid (2-Column Responsive)

**Purpose**: Relay control buttons in System tab

```css
.relays-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;  /* 12px */
}

@media (max-width: 720px) {
  .relays-grid {
    grid-template-columns: 1fr;  /* Single column on mobile */
  }
}
```

---

## 9. Spacing & Rhythm

### 9.1 Vertical Spacing

**Between KPI Row and Next Section**:
```html
<div style="display:flex;...;margin-bottom:12px;">...</div>
<hr class="separator" />
```

**Separator**:
```css
.separator {
  border: none;
  border-top: 1px solid #1e1e1e;
  margin: 16px 0;
}
```

**System Cards**:
```html
<div class="system-card" style="margin-bottom:20px;">...</div>
```

**Details Sections**:
```html
<details style="margin-top:12px;">...</details>
```

### 9.2 Internal Padding

**KPI Block**: `padding: 10px 12px`  
**System Card**: `padding: 16px` (via `--space-lg`)  
**Details Container**: `padding: 6px` (inner content)  
**Button**: `padding: 6px 14px` (standard), `4px 10px` (small)

### 9.3 Gap Values

- **KPI Row**: `gap: 12px`
- **System Card Header**: `gap: 10px`
- **Details Grid Column**: `column-gap: 10px`
- **Details Grid Row**: `row-gap: 8px`
- **Button with Icon**: `gap: 6px`

---

## 10. Examples by Tab

### 10.1 Sensors Tab

**KPI Row** (Colored blocks):
```html
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
  <div class="kpi" style="background:rgba(59,130,246,0.08);border-color:rgba(59,130,246,0.25);">
    <div class="kpi-label">pH</div>
    <div class="kpi-value" style="color:#60a5fa;">6.0</div>
  </div>
  <div class="kpi" style="background:rgba(34,197,94,0.08);border-color:rgba(34,197,94,0.25);">
    <div class="kpi-label">EC (µS/cm)</div>
    <div class="kpi-value" style="color:#22c55e;">1200</div>
  </div>
  <div class="kpi" style="background:rgba(251,146,60,0.08);border-color:rgba(251,146,60,0.25);">
    <div class="kpi-label">Temperature (°C)</div>
    <div class="kpi-value" style="color:#fb923c;">22.5</div>
  </div>
</div>
```

---

### 10.2 pH Tab

**Details Section** (Parameters):
```html
<details style="margin-top:12px;">
  <summary class="muted" style="cursor:pointer;font-size:var(--font-lg);">pH Parameters</summary>
  <div style="margin-top:12px;padding:6px;border-radius:8px;background:rgba(59,130,246,0.05);border:1px solid rgba(59,130,246,0.2);">
    <div class="muted" style="font-size:var(--font-sm);margin-bottom:12px;">
      Target pH range for auto-dosing. System doses pH UP when below pH Low.
    </div>
    <div style="display:grid;grid-template-columns:max-content max-content;column-gap:10px;row-gap:8px;align-items:center;">
      <label style="height:28px;width:120px;display:flex;align-items:center;">pH Low:</label>
      <input type="number" step="0.1" value="5.8" style="width:120px;height:28px;padding:0 6px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;" />
      
      <label style="height:28px;width:120px;display:flex;align-items:center;">pH High:</label>
      <input type="number" step="0.1" value="6.2" style="width:120px;height:28px;padding:0 6px;background:#1f2937;border:1px solid #374151;color:#e0e0e0;border-radius:6px;" />
    </div>
  </div>
</details>
```

---

### 10.3 System Tab

**System Card** (Raspberry Pi):
```html
<div class="system-card" style="margin-bottom:20px;">
  <div class="system-card-header">
    <span class="system-card-icon">🍓</span>
    <h4 class="system-card-title">Raspberry Pi</h4>
  </div>
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
    <div class="kpi">
      <div class="kpi-label">CPU Usage</div>
      <div class="kpi-value">12.3%</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">CPU Freq</div>
      <div class="kpi-value">1.5 GHz</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">CPU Temp</div>
      <div class="kpi-value">45.2°C</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Memory Used</div>
      <div class="kpi-value">1.2 GB</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Memory Total</div>
      <div class="kpi-value">4.0 GB</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Memory %</div>
      <div class="kpi-value">30%</div>
    </div>
  </div>
</div>
```

**Settings Section** (General):
```html
<div class="system-card" style="margin-bottom:20px;">
  <div class="system-card-header">
    <span class="system-card-icon">🏠</span>
    <h4 class="system-card-title">General Settings</h4>
  </div>
  <div class="muted" style="font-size:var(--font-sm);margin-bottom:var(--space-md);padding:8px 12px;background:rgba(59,130,246,0.05);border:1px solid rgba(59,130,246,0.15);border-radius:6px;">
    <strong>Note:</strong> Controller-specific settings are in their respective tabs.
  </div>
  <details style="margin-top:12px;">
    <summary class="muted" style="cursor:pointer;font-size:var(--font-lg);">General</summary>
    <div style="margin-top:12px;padding:6px;border-radius:8px;background:rgba(59,130,246,0.05);border:1px solid rgba(59,130,246,0.2);">
      <div class="muted" style="font-size:var(--font-xs);margin-bottom:var(--space-md);">
        Configure grow identification, timezone, and reservoir parameters.
      </div>
      <div id="settings-general">
        <!-- Populated by settings.js with 2-column grid -->
      </div>
    </div>
  </details>
</div>
```

---

## Compliance Checklist

When adding/modifying UI components, verify:

- [ ] **KPI blocks** use `.kpi` class with standard padding (10px 12px)
- [ ] **KPI labels** are uppercase, font-xs, letter-spacing 0.05em
- [ ] **KPI values** are font-size 0.95rem, font-weight 600
- [ ] **Colored KPIs** follow semantic colors (blue=pH/I²C, green=EC/GPIO, orange=temp, pink=power)
- [ ] **Details sections** use blue-tinted container (`rgba(59,130,246,0.05)`)
- [ ] **Details grids** use `max-content max-content` columns with 10px column gap, 8px row gap
- [ ] **Labels** in details grids are 120px wide, 28px tall
- [ ] **Inputs** in details grids are 120px wide, 28px tall
- [ ] **System cards** use `.system-card` class with margin-bottom 20px
- [ ] **Buttons** use `.btn-secondary` or `.btn-chip` with pill border-radius (999px)
- [ ] **Status badges** use `.ui-status-chip` with uppercase text
- [ ] **Spacing** follows standard gaps (12px KPI rows, 10px/8px grids, 20px cards)
- [ ] **Typography** uses CSS variables (--font-xs through --font-heading)
- [ ] **Colors** use CSS variables (--bg-pill, --fg-primary, --accent, etc.)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| v1.0 | 2025-11-23 | Initial lockdown after Phase 8 standardization | Copilot Agent |

---

## Approval

**Status**: ✅ **APPROVED FOR LOCKDOWN**

Any future UI changes must:
1. Reference this benchmark document
2. Justify deviations with formal design review
3. Update this document if new patterns emerge

**End of UI Template Benchmark**
