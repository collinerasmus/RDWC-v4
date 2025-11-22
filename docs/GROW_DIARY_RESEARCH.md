# Grow Diary & Historical Tracking — Research & Planning

## Current State (Phase 5: Schedule Controller)
✅ 12-week schedule timeline with phase tracking (seedling → veg → preflower → flower → flush)  
✅ Per-week targets: EC, pH band, temp, nutrients, lights  
✅ Current week KPI display  
⚠️ Notes field exists but limited to per-week technical notes (e.g., "Late flower - ripening phase")

## The Grow Diary Problem
**Core Need**: Capture observations, decisions, and outcomes throughout the grow cycle for:
- **Immediate troubleshooting**: "Why did pH drift on Day 23?"
- **Post-harvest analysis**: "Week 7 stretch was excessive — reduce N next time"
- **Knowledge transfer**: New growers learning from documented patterns
- **Compliance/audit**: Regulated environments need timestamped records

**Current Gap**: No dedicated place for:
- Daily/weekly observations (plant health, visual changes, environmental issues)
- Action logs (reservoir changes, equipment maintenance, interventions)
- Photo attachments with context (timelapse frames + notes)
- Retrospective analysis (harvest weight, potency, lessons learned)

## Industry Research: What Commercial Growers Track

### Essential Diary Entries (every grow facility does this)
1. **Daily Visual Inspections**
   - Leaf color, structure, pest signs
   - Root health (RDWC critical)
   - Water level, clarity
   
2. **Event Logging**
   - Reservoir changes (date, volume, EC before/after)
   - Nutrient adjustments (what, why, result)
   - Equipment issues/repairs
   - Environmental anomalies (temp spike, power outage)
   
3. **Weekly Measurements**
   - Plant height/canopy spread
   - Stem thickness
   - Bud development stage
   
4. **Harvest Data**
   - Wet/dry weight per plant
   - Trim waste %
   - Quality assessment (trichome density, aroma, potency if tested)

### Advanced Features (nice-to-have)
- **Timelapse Integration**: Link photos to diary entries (already planned for camera module)
- **Comparative Analytics**: Overlay sensor data (pH/EC/temp) with subjective notes to find correlations
- **Clone/Mother Plant Tracking**: Genealogy across grows (not auto-relevant but future photoperiod use)
- **Cost Tracking**: Nutrient usage, electricity, yield per dollar
- **Multi-Grow Comparison**: "This phenotype finished 5 days faster than last run"

## Architecture Options

### Option A: Extend Schedule Controller Tab
**Pros**: 
- Timeline already exists (week blocks)
- Contextual — notes are anchored to grow phases
- No new nav complexity

**Cons**:
- Clutters operational UI with retrospective data
- Week-level granularity (no daily entries)
- Harder to add photos, attachments

**Verdict**: ❌ Schedule tab should stay focused on **automation targets**, not observations.

---

### Option B: New "Grow Diary" Tab (Recommended)
**Pros**:
- Clean separation: automation vs. documentation
- Can support daily entries (not just weekly)
- Room for rich features (photos, tags, search)
- Doesn't interfere with controller logic

**Cons**:
- Adds another tab (but justified — diary is core to grower workflow)

**Verdict**: ✅ **Best fit.** Diary is important enough to warrant dedicated space.

---

### Option C: Overview Dashboard Widget
**Pros**:
- Quick access to recent notes
- Combines with sensor trends for context

**Cons**:
- Limited space for detailed entries
- Hard to browse historical data

**Verdict**: ⚠️ Hybrid approach: Recent entries summary on Overview, full diary in dedicated tab.

---

## Recommended Implementation Plan

### Phase 6: Grow Diary (MVP)
**Goal**: Capture text-based observations anchored to grow timeline.

#### Backend (`app/diary_api.py`)
```python
# SQLite schema
CREATE TABLE diary_entries (
    id INTEGER PRIMARY KEY,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    grow_day INTEGER,  -- calculated from grow_start_date
    week INTEGER,      -- 1-12
    entry_type TEXT,   -- observation|action|measurement|issue|harvest
    title TEXT,
    body TEXT,
    tags TEXT,         -- JSON array: ["pH_drift", "nutrient_burn"]
    author TEXT DEFAULT 'operator'
)
```

**Endpoints**:
- `GET /api/diary?week={n}&type={type}&limit=50` — list entries
- `POST /api/diary` — add entry
- `PUT /api/diary/{id}` — edit entry
- `DELETE /api/diary/{id}` — remove entry

#### Frontend (new `diary.js` + `index.html` tab)
**UI Layout**:
```
┌─────────────────────────────────────────────┐
│ Grow Diary                            🔍 Search │
├─────────────────────────────────────────────┤
│ Timeline View: [Day] [Week] [All]          │
│ Filter: [Type ▾] [Tags]                    │
├─────────────────────────────────────────────┤
│ ┌─ Day 39 (Week 6) ── 2025-11-20 14:30 ──┐ │
│ │ 📝 Observation: Pre-flower stretch      │ │
│ │ Plants showing first pistils. Increased │ │
│ │ vertical growth 3cm since yesterday.    │ │
│ │ Tags: [preflower] [stretch]             │ │
│ └─────────────────────────────────────────┘ │
│ ┌─ Day 37 (Week 6) ── 2025-11-18 09:15 ──┐ │
│ │ ⚙️ Action: Reservoir change             │ │
│ │ Full drain/refill. EC 1.4 → 1.5.        │ │
│ │ Added 200ml Grow, 150ml Micro, 250ml B │ │
│ │ Tags: [maintenance] [nutrients]         │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ [+ New Entry]                               │
└─────────────────────────────────────────────┘
```

**Entry Types** (color-coded):
- 📝 **Observation**: Visual inspections, plant health
- ⚙️ **Action**: Reservoir changes, dosing, pruning
- 📏 **Measurement**: Manual height/weight checks
- ⚠️ **Issue**: Problems, errors, troubleshooting
- 🏆 **Harvest**: Final results, weights, quality notes

---

### Phase 7: Photo Integration
**Goal**: Attach camera snapshots to diary entries.

**Enhancement**:
- Add `photo_path` field to `diary_entries` table
- Button in diary form: "📷 Capture & Attach" → calls `/camera/snapshot` → stores path
- Thumbnail preview in entry card, click to enlarge
- Timelapse video linked to week entries

---

### Phase 8: Analytics & Insights
**Goal**: Cross-reference diary with sensor data.

**Features**:
- Overlay EC/pH/temp graphs with diary event markers
- "What happened on Day 23?" → show sensor anomalies + diary notes
- Harvest report: auto-generate summary from diary tags + sensor stats

---

## Validation Criteria for Dedicated Diary Tab

✅ **High-value use case**: Post-harvest analysis drives 20-30% yield improvements (industry standard).  
✅ **Frequent usage**: Growers log 1-3 entries/day during active phases.  
✅ **Rich data type**: Text, tags, photos, timestamps — not suited for inline schedule notes.  
✅ **Long-term retention**: Needs multi-grow browsing, search, export (CSV/PDF reports).  
✅ **No operational coupling**: Diary doesn't affect automation — safe to separate.

**Conclusion**: Diary deserves its own tab. It's core to grower workflow but orthogonal to control logic.

---

## Quick Wins (Do Now)
1. ✅ **Capture this research doc** (done — you're reading it)
2. ⚠️ **Add placeholder tab** in `index.html` with "Coming Soon" message
3. ⚠️ **Update PROJECT_MANAGEMENT.md** with Phase 6-8 roadmap

## Don't Break Current Work
- Schedule Controller (Phase 5) is automation-focused — leave it alone
- Diary is **additive** — no changes to existing tabs/APIs
- Can prototype diary backend without touching UI until Phase 6

---

## Open Questions
1. **Multi-grow support**: Track multiple cycles? (Probably overkill for single-tent hobbyist, but commercial needs it)
2. **Export formats**: PDF report? CSV for Excel? (Low priority)
3. **Mobile access**: Growers often check plants with phone — responsive design critical
4. **Voice notes**: Speak observations while hands are dirty? (Future: use browser SpeechRecognition API)

---

## Next Steps
**Immediate** (don't derail Phase 5):
- [x] Document diary research (this file)
- [ ] Add "Diary (Coming Soon)" tab to UI (5 min task)
- [ ] Update roadmap in PROJECT_MANAGEMENT.md

**Phase 6 Kickoff** (after Schedule Controller is stable):
- [ ] Design SQLite schema for diary_entries
- [ ] Implement diary_api.py with CRUD endpoints
- [ ] Build diary.js with timeline view + entry form
- [ ] Manual testing: add 10-15 sample entries, verify search/filter

---

## References
- [Cannabis Cultivation Log Templates](https://www.cannabisbusinesstimes.com/article/cultivation-logs/)
- [Commercial Grow Facility Best Practices](https://www.maximumyield.com/record-keeping-for-cannabis-cultivation/2/4023)
- RDWC-specific: Root health inspections every 3-4 days critical for DWC systems

---

**Status**: Research complete. Ready to proceed with dedicated Diary tab in Phase 6.
