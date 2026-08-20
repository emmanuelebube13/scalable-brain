# Scalable Brain — Enterprise UX Architecture & Information Design

**Document Version**: 1.0  
**Last Updated**: May 7, 2026  
**Scope**: Frontend UX flows, information architecture, interaction patterns, and accessibility standards

---

## Executive Overview

Scalable Brain is a complex, layered quantitative trading system. The frontend serves three distinct user personas:

- **Researchers**: Explore strategy qualification data, design rule sets, compare backtests
- **Operators**: Monitor live execution, track performance, triage alerts
- **Architects**: Review system contracts, inspect data lineage, validate schema alignment

This document establishes a **unified navigation model**, **consistent interaction patterns**, and **accessible, responsive UI conventions** that scale across all pages while maintaining clarity for different user goals.

---

## 1. Navigation Architecture

### 1.1 Global Navigation Model

**Topology**: Hub-and-spoke with breadcrumb trail

```
Index (Hub)
├── Research Hub
│   ├── Research Notes (CRUD)
│   └── Note Detail (Read-Only)
├── Overview Dashboard
│   ├── System Status
│   └── Performance Snapshot
├── Strategy Lab
│   ├── Trend Strategies
│   └── Range Strategies
├── Architecture Portal
│   ├── System Diagram
│   └── Layer Reference
└── Data References
    ├── ERD Interactive
    ├── Forex Timezones
    └── System Tree Guide
```

### 1.2 Topbar / Header Structure

**Sticky header (68px fixed height at desktop, 56px mobile)**

```
[Logo/Brand Mark] [Page Title]     [Back Link] [Current Breadcrumb]
                                    [Search Toggle]
```

**Components**:
- **Brand Mark** (left): 36px logo + "Scalable Brain" text (desktop only; logo-only on mobile < 640px)
- **Page Title** (center-left): Large, wayfinding-focused (e.g., "Research Hub", "Strategy Lab")
- **Breadcrumb Trail** (right of title on desktop, collapsed to back button on mobile):
  - Format: `Index > Research > Notes`
  - Each segment is a clickable link (except current page, which is text)
  - Mobile (< 1024px): Show only `<< Back to [Parent]` button
  - Desktop (≥1024px): Full breadcrumb visible
- **Secondary Actions** (right):
  - Search icon (toggles inline search bar below header)
  - Filter/sort icon (context-dependent)
  - No more than 3 icons; rest in hamburger menu on mobile

**Accessibility**:
- `<header role="banner">` wraps entire topbar
- Breadcrumb is `<nav aria-label="Breadcrumb">` with `aria-current="page"` on last item
- Sticky positioning: add `aria-live="polite"` if topbar state changes

### 1.3 Breadcrumb Strategy

**Rules**:
- Always show parent chain (minimum 2 levels)
- Current page is text, not a link
- If breadcrumb exceeds 5 segments, truncate to: `Home ... > Parent > Current`
- On mobile, replace with single back button: `← Back to Research Hub`
- Use forward slash `/` as visual separator (CSS-generated with `::after`)

**Example flows**:
1. Index → Research Hub → New Note modal
   - Breadcrumb: `Index / Research / New Note`
   
2. Index → Overview → System Status drill-down
   - Breadcrumb: `Index / Overview / Status`
   
3. Index → Architecture → ERD Detail
   - Breadcrumb: `Index / Architecture / ERD`

### 1.4 Left Sidebar (Optional, Desktop ≥1200px)

**Use case**: Research Hub benefits from persistent section navigation

```
Search notes
───────────────────────
📌 Recent (3 items)
───────────────────────
📋 By Category
   ├─ Macro Analysis
   ├─ Signal Design
   ├─ Risk Models
   └─ Execution
───────────────────────
📊 By Layer
   ├─ Layer 0 (Qualification)
   ├─ Layer 2 (Signals)
   ├─ Layer 3 (ML)
   └─ Layer 4 (Execution)
───────────────────────
🔖 Pinned (User's favorites)
───────────────────────
📅 Date Range
   [Picker]
───────────────────────
🏷️  Tags
   [Multi-select]
```

**Behavior**:
- Sticky, stays in viewport during vertical scroll
- Collapses to hamburger icon on tablet (768–1199px)
- Hides completely on mobile (< 768px)
- Width: 240px on desktop, takes full width when expanded on mobile
- Background: Slightly darker (--bg-card with 0.5 opacity border) to distinguish from main content

**Performance**: Filter selections update main grid in place; no full-page reload

---

## 2. Research Notes Page Redesign

### 2.1 Recommended Layout: **Sidebar + Main Grid**

**Desktop (≥1200px)**:
```
┌─ Topbar (back to Index, title, search toggle) ─────────────────────┐
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [Sidebar: filters]    [Main: Grid view]                            │
│  ┌──────────────┐      ┌─────────────────────────────────────────┐ │
│  │ Search       │      │ [Ctrl+K New Note] [↓ Sort] [⚙️  Filter]  │ │
│  │ Categories   │      ├─────────────────────────────────────────┤ │
│  │ Layers       │      │ Card | Card | Card                      │ │
│  │ Pinned       │      │ ┌─────┐ ┌─────┐ ┌─────┐                 │ │
│  │ Date Range   │      │ │Note │ │Note │ │Note │ ...            │ │
│  │ Tags         │      │ │[⋯]  │ │[⋯]  │ │[⋯]  │                 │ │
│  └──────────────┘      │ └─────┘ └─────┘ └─────┘                 │ │
│                        │                                           │ │
│                        │ Pagination: [1] 2 3 ... Last [→]        │ │
│                        └─────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Tablet (768–1199px)**:
```
┌─ Topbar ─────────────────────┐
├───────────────────────────────┤
│ [≡ Filters]  [Grid]           │
│                               │
│ Card | Card | Card           │
│ ┌────┐ ┌────┐ ┌────┐         │
│ │Note│ │Note│ │Note│         │
│ └────┘ └────┘ └────┘         │
└───────────────────────────────┘
```

Filters collapse into drawer; toggle with hamburger icon.

**Mobile (< 768px)**:
```
┌─ Topbar ────────────────┐
├─────────────────────────┤
│ [≡ Menu]  [Ctrl+K New]  │
├─────────────────────────┤
│ Card (full width)       │
│ ┌────────────────────┐  │
│ │ Note Title         │  │
│ │ Category Badge     │  │
│ │ [View] [Edit]      │  │
│ └────────────────────┘  │
│                         │
│ Card (full width)       │
│ ...                     │
└─────────────────────────┘
```

Cards stack vertically. Filters accessible via menu drawer.

### 2.2 Card-Based Display (Primary)

**Why over table**: Research notes are heterogeneous (different lengths, rich metadata). Cards provide:
- Better scan-ability on mobile
- Room for preview, tags, action buttons
- Natural visual hierarchy

**Card anatomy** (320px desktop, 100% mobile):

```
┌─────────────────────────────────┐
│ ⭐ [Title / Research Topic]     │  (title is clickable → detail page)
├─────────────────────────────────┤
│ Macro Analysis                   │  (category badge, light background)
├─────────────────────────────────┤
│ [Preview text, 2 lines max]     │
│ "Interest rate implications     │
│  for trend signal desensitiz..." │
├─────────────────────────────────┤
│ Layer 2 • Updated 2 days ago    │  (metadata: layer, timestamp)
├─────────────────────────────────┤
│ [View] [Edit] [⋯ More]         │  (action buttons: primary, secondary, menu)
└─────────────────────────────────┘
```

**Card states**:
- **Normal**: Box shadow, light border, white background
- **Hover**: Slightly raised shadow, border brightens, cursor pointer
- **Selected** (if bulk actions enabled): Blue left border (5px), subtle background tint
- **Archived**: Opacity 0.6, striped background pattern
- **Loading**: Skeleton placeholder with pulsing gradient

**Interaction**:
- Click card body → navigate to detail page (read-only view)
- Click title → same as body
- Hover footer buttons appear more prominent (darker text, cursor changes)

### 2.3 Display Mode Toggle (Optional Enhancement)

**If research hub becomes complex**, offer view toggle:

```
[View:  ≣ List | ≡ Grid | ≰ Tree]
```

- **Grid**: Default, card-based (as designed above)
- **List**: Condensed table format (title, category, layer, updated, actions)
- **Tree**: Hierarchical by layer, then category (useful for large research corpus)

Each view preserves active filters and sort.

### 2.4 Sorting & Filtering

**Sorting** (dropdown in header):
- Default: `Updated (newest first)`
- Options:
  - Created (newest first)
  - Title (A–Z)
  - Layer (0 → 4)
  - Category (alphabetical)

**Filtering** (sidebar on desktop, drawer on mobile):
- **Category**: Multi-select checkboxes (Macro Analysis, Signal Design, Risk Models, Execution)
- **Layer**: Radio buttons (Layer 0, 1, 2, 3, 4, or "All")
- **Date Range**: Picker (From / To, with "Last 7 days", "This month" presets)
- **Tags**: Auto-complete multi-select
- **Status**: Checkbox (Active, Archived)

**Applied filters**: Show as removable "pills" above the grid:
```
[✕ Macro Analysis] [✕ Layer 2] [✕ Last 7 days]  [Clear All]
```

**Search** (persistent inline box in header):
- Real-time filtering (as user types)
- Searches: title, preview, tags, category name
- Icon: magnifying glass (⌘+F or Ctrl+F shortcut)
- Debounce 300ms to avoid excessive re-renders

### 2.5 Create/Edit Note Flow

**Primary entry**: "New Note" button (Ctrl+K / Cmd+K shortcut)

**Two design options**:

#### **Option A: Modal (Lightweight)**
- Pros: Non-destructive, easy context switching, familiar
- Cons: Covers main content; feels constraining on small screens

```
┌──────────────────────────────────┐
│ ✕  New Research Note             │
├──────────────────────────────────┤
│ Title *                           │
│ [                              ] │
│ Category *                        │
│ [Dropdown: --]                    │
│ Layer *                           │
│ [Radio: ○ 0  ○ 1  ○ 2  ○ 3  ○ 4]│
│ Content *                         │
│ [Large text area]                 │
│ │ Rich editor, Markdown support   │
│ │ (headings, bold, lists, code)   │
│                                  │
│ Tags (optional)                   │
│ [Multi-select with suggestions]   │
│                                  │
│ Internal Links (optional)         │
│ [+ Add link to another note]      │
│                                  │
│ [Cancel]           [Save] [Save & New]  │
└──────────────────────────────────┘
```

**Behavior**:
- All fields except Tags/Links marked with `*` (required)
- Tab order: Title → Category → Layer → Content → Tags → Links → Buttons
- Escape key closes (warns if unsaved changes)
- On save: Toast confirmation, redirect to detail page or grid
- On "Save & New": Reset form, keep category/layer if possible

#### **Option B: Inline Page (Immersive)**
- Pros: More space, less modal friction, better for power users
- Cons: Replaces main view; requires back button to return

**Recommendation**: Use **Option A (Modal)** for quick edits; use Option B as a secondary full-screen option ("Open in Editor" button from modal).

### 2.6 Keyboard Shortcuts

Research Hub should be power-user friendly:

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` / `Cmd+K` | New Note modal |
| `Ctrl+F` / `Cmd+F` | Focus search box |
| `/` | Focus search box (alternative, like GitHub) |
| `↑` / `↓` | Navigate between cards (with focus indicator) |
| `Enter` | Open focused card detail |
| `E` | Edit focused card (opens modal) |
| `A` | Archive focused card (with undo toast) |
| `?` | Show keyboard help modal |
| `Esc` | Close modal or unfocus |

**Implementation**:
- Attach keyboard listeners at `document` level
- Only activate when focus is not in input/textarea
- Show visual indicator (e.g., "Press ? for help") in UI corner

---

## 3. Dashboard / Overview Page

### 3.1 Page Structure

**Hero Section** (top-of-page, minimal scroll):

```
┌──────────────────────────────────────────────────────────────────┐
│                    [Topbar w/ breadcrumb]                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│                    Scalable Brain Status                         │
│                Live Trading System Performance                   │
│                                                                  │
│          [Primary CTA: Go to Research] [Secondary: Docs]         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Stats Section** (4 columns on desktop, 2 on tablet, 1 on mobile):

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  🎯 Signal  │ 📊 ML Model │ ⚡ Trades   │ 📈 Return   │
│  Accuracy   │  Confidence │  Executed   │  This Month │
│   87.3%     │    91.2%    │   1,247     │   +4.2%     │
│ ↑ +2.1%     │ ↓ -1.3%     │ ↑ +156     │ ↑ +1.8%     │
│ vs last mo. │ vs last mo. │ vs last mo. │ vs last mo. │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

**Quick Links Section** (below stats):

```
Recent Activity & Actions
┌──────────────────────────────────────────────────┐
│ ⏱️ Last Layer 4 run: 6 hours ago (48 trades)     │
├──────────────────────────────────────────────────┤
│ ⚠️ Alerts: 3 pending (1 high priority)            │
├──────────────────────────────────────────────────┤
│ [→ View All Trades] [→ View Alerts]              │
│ [→ Open Research Hub] [→ System Status]          │
└──────────────────────────────────────────────────┘
```

### 3.2 Hero Section Design

**Visual Approach**: Gradient background with accent color, minimal text, clear hierarchy

```
Hero Container (height: 280px, padding: 60px 24px)
├─ Background: Linear gradient (135deg, brand color → darker shade)
├─ OR: Subtle animated mesh gradient (CSS or SVG)
└─ Overlay: Faint pattern (grid, dots, or waves) at 5% opacity

Content (centered, max-width 720px):
├─ Eyebrow: "Quantitative Trading Platform" (small caps, secondary color)
├─ H1: "Scalable Brain Status" (white text, 2.5rem, bold)
├─ Subtitle: "Real-time system performance and trading insights" (light gray, 1.1rem)
└─ CTAs:
   ├─ Primary: "Explore Research Hub" (solid white text, brand-colored bg, 16px font)
   └─ Secondary: "View Documentation" (white text, transparent, 1px white border)
```

**Accessibility**:
- Ensure sufficient contrast (WCAG AA minimum 4.5:1 for text on gradient)
- Use `role="region" aria-label="Dashboard Hero"` for screen readers
- Text is actual text, not background image (searchable, copyable)

### 3.3 Stats Cards

**Design** (each card):

```
┌─ Card header (icon + label) ────────────────────┐
│ 📊 Metric Label                                 │
├─────────────────────────────────────────────────┤
│                                                 │
│           Large, bold metric value              │
│              87.3% / 1,247 / +4.2%              │
│                                                 │
├─────────────────────────────────────────────────┤
│  ↑ +2.1% vs last month  │  Updated: 2h ago    │
└─────────────────────────────────────────────────┘
```

**Metrics to display** (prioritize by role):

1. **Signal Accuracy** (87.3%)
   - Definition: Signals that resulted in profitable trades / total signals
   - Trend: ↑ +2.1% (green)
   - Update freq: End of day

2. **ML Model Confidence** (91.2%)
   - Definition: Average probability threshold for gatekeeper model
   - Trend: ↓ -1.3% (red)
   - Update freq: Hourly

3. **Trades Executed** (1,247)
   - Definition: Total trades executed this month
   - Trend: ↑ +156 vs last month
   - Update freq: Real-time (live pulse indicator)

4. **Monthly Return** (+4.2%)
   - Definition: Realized P&L this month / starting capital
   - Trend: ↑ +1.8% vs last month
   - Update freq: Daily (end of day)

**Card states**:
- **Data loaded**: Full content visible, slight shadow
- **Loading**: Skeleton (gray bar, 60% width, pulsing)
- **Error**: Icon (⚠️) + message ("Failed to load. Try again.") with retry button
- **Stale**: Muted opacity + "Data as of 8h ago" timestamp

### 3.4 Recent Activity & Alerts

**Layout** (vertical stack, each 60px height):

```
Activity Item:
┌────────────────────────────────────────┐
│ ⏱️ Label                         Time   │
│ Layer 4 pipeline completed    6h ago   │
│ 48 trades generated (8 skipped)        │
│ [→ View details]                       │
└────────────────────────────────────────┘

Alert Item (if severity = high):
┌────────────────────────────────────────┐
│ ⚠️ [HIGH] Alert Label          Now     │
│ Unusual drawdown detected              │
│ [Investigate] [Acknowledge]            │
└────────────────────────────────────────┘
```

**Actions**:
- View Details: Navigate to dedicated page (e.g., trade log, alert detail)
- Acknowledge: Mark alert as seen; removes urgency highlight
- Retry: For failed operations (re-run Layer 4, etc.)

### 3.5 Call-to-Action Placement

**Primary CTA**: "Explore Research Hub"
- Position: Hero section, prominent button
- Copies researcher to `/research.html` with filters pre-populated if relevant

**Secondary CTAs** (below activity):
- "View All Trades" → Link to execution telemetry page
- "View System Alerts" → Link to alert center
- "System Architecture" → Link to `/architecture.html`
- "Documentation" → Link to external docs or `/docs` page

**Mobile (< 768px)**:
- Stack CTAs vertically (full width on mobile)
- Hero height reduced to 220px
- Stats cards to 2-column grid instead of 4

---

## 4. Empty States & Loading States

### 4.1 Empty State Patterns

**Empty Research Hub** (no notes created yet):

```
┌────────────────────────────────────────┐
│                                        │
│           📝 No Research Notes         │
│                                        │
│    Start by creating your first        │
│      research note to track            │
│   insights, test ideas, and log        │
│    findings from your analysis.        │
│                                        │
│        [✨ Create First Note]           │
│        [Learn more →]                  │
│                                        │
└────────────────────────────────────────┘
```

**Empty Results** (after filtering):

```
┌────────────────────────────────────────┐
│                                        │
│        🔍 No Notes Found               │
│                                        │
│    Try adjusting your filters:         │
│    • Clear the date range              │
│    • Remove category filters           │
│    • Search for a keyword              │
│    • Check archived notes              │
│                                        │
│   [Clear Filters] [Reset Search]       │
│                                        │
└────────────────────────────────────────┘
```

**Error State** (data fetch failed):

```
┌────────────────────────────────────────┐
│                                        │
│        ⚠️ Failed to Load                │
│                                        │
│    We couldn't fetch your research     │
│    notes. This might be a temporary    │
│    issue. Please try again.            │
│                                        │
│         [↻ Retry] [Go Home]            │
│                                        │
└────────────────────────────────────────┘
```

**Design principles for empty states**:
- Use clear, supportive icon (not generic "no data" symbol)
- Empathetic copy (avoid "no results", use "let's create" messaging)
- Always suggest next steps (CTA button)
- Show filters/search UI even in empty state (user can adjust)
- Background: Subtle pattern (dots, grid) at low opacity to indicate space

### 4.2 Loading State Patterns

**Full page load** (initial navigation):

```
┌──────────────────────────────────────┐
│ [Topbar with logo]                   │
├──────────────────────────────────────┤
│                                      │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░      │  (skeleton)
│ ░░░░░░░░░░░░░░                       │
│                                      │
│ ░░░░ ░░░░ ░░░░ ░░░░                  │
│ ░░░░ ░░░░ ░░░░ ░░░░                  │  (card placeholders)
│ ░░░░ ░░░░ ░░░░ ░░░░                  │
│                                      │
└──────────────────────────────────────┘
```

**Skeleton UI approach**:
- Use `<div class="skeleton" />` placeholders matching expected layout
- Gradient pulse animation: `background: linear-gradient(90deg, #f0f0f0, #e0e0e0, #f0f0f0); background-size: 200% 100%; animation: pulse 2s infinite;`
- Never show generic spinners; skeletons are faster-perceived

**Inline loading** (filter applied, data fetching):

```
Apply filter → Brief delay (100ms) → Cards fade to 50% opacity, 
              skeleton overlay appears on each card
              Progress: "Loading 2,456 notes..." (bottom right)
Data arrives → Fade in, skeleton removed
```

**Incremental loading** (infinite scroll or pagination):

```
User scrolls near pagination button or bottom
→ Show: "[↻ Loading more...]" with spinner
→ New cards append below
→ Smooth scroll to first new card
```

---

## 5. Form Design

### 5.1 Research Note Creation/Edit Form

**Field groups**:

```
METADATA GROUP
├─ Title (required)
├─ Category (required)
└─ Layer (required)

CONTENT GROUP
├─ Content (required, rich text)
├─ Tags (optional, multi-select)
└─ Internal Links (optional)

ADDITIONAL GROUP
├─ Status (default: "Active")
├─ Visibility (default: "Private")
└─ Related Research (optional, autocomplete)

ACTIONS GROUP
├─ [Cancel]
├─ [Save Draft]
└─ [Publish]
```

### 5.2 Form Field Design

**Text input (Title, etc.)**:

```
Title *                          ← Label with required indicator
[                              ]
 Enter a clear, descriptive title.  ← Helper text below input
 Max 120 characters.                ← Character counter
```

**Dropdown (Category)**:

```
Category *
[Select a category ▼]
```

On focus:
```
[◄ Select a category ▲]
├─ Macro Analysis
├─ Signal Design
├─ Risk Models
└─ Execution
```

**Radio group (Layer)**:

```
Layer *
○ Layer 0 (Qualification)
○ Layer 1 (Regime)
○ Layer 2 (Signals)
○ Layer 3 (ML Training)
○ Layer 4 (Live Execution)
```

**Rich Text Editor (Content)**:

```
Content *
┌──────────────────────────────┐
│ [B] [I] [U] [Code] [Link] [+] │ ← Toolbar
├──────────────────────────────┤
│ [Large editable area]         │
│ Markdown + WYSIWYG support    │
│ Ctrl+B for bold, Cmd+/ help   │
│                               │
│                               │
└──────────────────────────────┘
 Preview will appear below on blur.
```

**Multi-select (Tags)**:

```
Tags (optional)
[Add tags ▼]

On focus/type:
[research, signal, indicator ▼]
├─ research (3 existing)
├─ signal (8 existing)
├─ indicator (12 existing)
├─ ─────────────────────
└─ [✓ research] [+ New Tag]
```

**Validation & feedback**:

| Field | Validation | Error Message |
|-------|-----------|------------------|
| Title | Required, max 120 chars | "Title is required" or "Title must be ≤ 120 characters" |
| Category | Required | "Please select a category" |
| Layer | Required | "Please select a layer" |
| Content | Required, min 20 chars | "Content required (min 20 characters)" |
| Tags | Optional, max 10 tags | "Maximum 10 tags allowed" |

**Real-time validation**:
- Check as user leaves field (onBlur)
- Show inline error message in red below field
- Disable submit button if form invalid
- Clear error on correction

### 5.3 Form States

**Idle** (not focused, no error):
```
[Border: light gray, 1px]
Background: white
Text: dark gray
```

**Focus** (focused, no error):
```
[Border: brand blue, 2px]
Background: white
Box-shadow: 0 0 0 3px rgba(brand, 0.1)
Text: dark gray
```

**Error** (validation failed):
```
[Border: red, 2px]
Background: #fff5f5
Box-shadow: 0 0 0 3px rgba(red, 0.1)
Error text below: red, 0.9rem
Icon: ⚠️ in field
```

**Disabled** (e.g., form submitting):
```
[Border: light gray, 1px]
Background: #f5f5f5
Opacity: 0.6
Cursor: not-allowed
```

### 5.4 Required Field Indicators

**Strategy**: Asterisk + text label

```
Title *
[Label text] (small, gray, "Required")
```

**Why asterisk + label**: Redundancy helps non-visual users (asterisk alone is not sufficient per WCAG).

**Hint text styling**:
- Color: --text-light (gray)
- Font-size: 0.85rem
- Margin-top: 4px
- Always below the input

### 5.5 Helper Text & Guidance

**Inline hints** (under field):
```
Title *
[                              ]
 Pro tip: Use keywords from your analysis for better searchability.
```

**Tooltips** (hover on icon):
```
Internal Links (optional) [ⓘ]

On hover:
┌──────────────────────────────┐
│ Link to related research     │
│ notes to create a knowledge  │
│ graph. Use for              │
│ cross-referencing insights.  │
└──────────────────────────────┘
```

**Contextual popover** (before first-time edit):
```
New to research notes? [×]
┌────────────────────────────────┐
│ Tips for effective notes:       │
│ • Be specific in titles        │
│ • Reference data/sources       │
│ • Tag liberally for discovery  │
│ • Link to related research     │
│                               │
│ [Learn more] [Dismiss]        │
└────────────────────────────────┘
```

---

## 6. Link / Button Taxonomy

### 6.1 Button Types & Prominence

**Hierarchy** (based on action importance):

#### **Primary Button** (high importance, rare per page)

```
Background: Linear gradient (brand blue → darker blue)
Text: White, 600 weight, 14px
Padding: 12px 24px
Border-radius: 10px
Border: None
Cursor: pointer
```

**States**:
- **Hover**: Lift shadow, slight background brightening
- **Active**: Shadow recessed, slight opacity increase
- **Disabled**: Opacity 0.5, cursor not-allowed

**Usage**: 
- Create new resource ("New Note", "Start Research")
- Confirm destructive action ("Delete Permanently")
- Submit critical forms

#### **Secondary Button** (moderate importance)

```
Background: White
Border: 1px solid --border-color
Text: --text (dark), 600 weight, 14px
Padding: 12px 24px
Border-radius: 10px
Cursor: pointer
```

**States**:
- **Hover**: Background lighten, border darken
- **Active**: Background slightly darker
- **Disabled**: Opacity 0.5, cursor not-allowed

**Usage**:
- Cancel operations
- View details
- Apply filters
- Non-critical navigation

#### **Tertiary Button** (low importance, deemphasized)

```
Background: Transparent
Border: None
Text: --primary-color (brand blue), 500 weight, 14px
Text-decoration: underline (subtle, appears on hover)
Padding: 8px 12px
Cursor: pointer
```

**States**:
- **Hover**: Text color darken, underline visible
- **Active**: Slight background tint (0.05 opacity)
- **Disabled**: Opacity 0.5, cursor not-allowed

**Usage**:
- Help links ("Learn more", "What's this?")
- Optional secondary actions
- Undo/redo
- Dismiss notifications

#### **Danger Button** (destructive actions)

```
Background: Red (--danger: #ef4444)
Text: White, 600 weight, 14px
Padding: 12px 24px
Border-radius: 10px
Border: None
Cursor: pointer
```

**States**:
- **Hover**: Darker red background, shadow lift
- **Active**: Shadow recessed
- **Disabled**: Opacity 0.5

**Usage**:
- Delete note
- Archive research
- Clear data
- Irreversible actions

### 6.2 Button Sizing

**Desktop**:
- **Large**: 48px height (for primary CTAs in hero)
- **Default**: 36px height (typical form buttons)
- **Small**: 28px height (inline, secondary actions)

**Mobile**: 
- **Touch target minimum**: 48px × 48px (WCAG requirement)
- Increase padding/height on mobile to ensure easy tapping
- Never use smaller than 28px height

**Width conventions**:
- **Full-width** (on mobile, < 640px): Buttons span container width (minus padding)
- **Fixed-width** (on desktop): Determined by content + padding, but typically 120–180px
- **Flex-width**: Button expands to fill space if grouped with other buttons

### 6.3 Links (Text-Only Navigation)

**Inline links** (within body text):

```
Styling:
├─ Color: --primary (brand blue)
├─ Text-decoration: underline (faint, appears on hover)
├─ Cursor: pointer
└─ Font-weight: inherit (don't bold links in body)

Hover state:
├─ Color: darken to --primary-dark
└─ Text-decoration: underline (solid)

Visited state:
├─ Color: --primary-dark (same as hover; don't track visited)
```

**Navigation links** (topbar, breadcrumb):

```
Styling:
├─ Color: --text-light (not blue, part of navigation structure)
├─ Font-weight: 500
├─ Text-decoration: none
└─ Padding: 8px 4px

Hover state:
├─ Color: --primary (turn blue)
└─ Cursor: pointer

Active state (current page):
├─ Color: --text (darker)
├─ Font-weight: 600
└─ Underline: thin, --primary (optional, context-dependent)
```

### 6.4 When to Use Buttons vs Links

| Scenario | Button | Link |
|----------|--------|------|
| Submit a form | ✓ | ✗ |
| Navigate to a page | ✗ | ✓ |
| Trigger a modal | ✓ | ✗ |
| External URL | ✗ | ✓ (with `target="_blank"`) |
| Collapse/expand section | ✓ | ✗ |
| Download a file | ✓ | ✗ |
| Change a view (grid ↔ table) | ✓ | ✗ |
| Breadcrumb navigation | ✗ | ✓ |
| Inline emphasis in text | ✗ | ✓ |

**Rule of thumb**: If it triggers a state change, use a button. If it navigates, use a link.

### 6.5 Button Groups & Icon Usage

**Icon placement**:
- **Left icon** (primary): For action verbs
  ```
  [➕ New Note] [📁 Open Folder] [🔍 Search]
  ```

- **Right icon** (secondary): For navigation cues
  ```
  [View Details →] [Learn More →] [Open ↗]
  ```

- **Icon-only button**: Only if icon is universally recognizable
  ```
  [⋯] for "More actions"
  [❌] for "Close"
  [✓] for "Confirm"
  ```
  **MUST have `aria-label`** for screen readers: `<button aria-label="More options">⋯</button>`

**Button groups** (e.g., Save vs Cancel):

```
[← Cancel]  [✓ Save]
```

- Group related buttons with consistent height
- Separate primary from secondary with whitespace (12px gap)
- On mobile, stack vertically (full-width):
  ```
  [← Cancel]
  [✓ Save]
  ```

---

## 7. Page Transitions & Motion

### 7.1 Navigation Transitions

**Default transition** (all page changes):

```
1. User clicks link/button
   ↓
2. (Optional) Show loading indicator (fade in 300ms)
   ↓
3. Content fades out (opacity: 1 → 0 over 200ms)
   ↓
4. Page URL changes, new content loads
   ↓
5. Content fades in (opacity: 0 → 1 over 300ms)
   ↓
6. Scroll to top (instant or smooth, user preference)
```

**Fade transition CSS**:
```css
.page-content {
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

### 7.2 Modal Transitions

**Enter** (when modal opens):
```
1. Backdrop fades in (opacity: 0 → 0.5 over 200ms, easing: ease-out)
2. Modal scales in and fades (transform: scale(0.95) → 1, opacity: 0 → 1 over 300ms, easing: cubic-bezier(0.4, 0, 0.2, 1))
3. Focus shifts to close button or first form field
```

**Exit** (when modal closes):
```
1. Modal scales out and fades (transform: scale(1) → 0.95, opacity: 1 → 0 over 200ms)
2. Backdrop fades out (opacity: 0.5 → 0 over 200ms)
3. Focus returns to trigger button
```

### 7.3 Loading Indicators

**Use case 1: Page load (initial navigation)**
- Show skeleton UI (preferred)
- If skeleton unavailable, show minimal spinner (16px, centered in content area)

**Use case 2: Incremental data fetch (filter applied)**
- Show 50% opacity overlay on affected cards
- Mini skeleton placeholders on cards

**Use case 3: Async action (uploading, saving)**
- Inline progress bar below button:
  ```
  [💾 Saving...]
  ▓▓▓▓▓▓░░░░░ 65%
  ```
- Or: Toast notification with progress

### 7.4 Toast Notifications

**Position**: Bottom-right (desktop), bottom-center (mobile)  
**Z-index**: 10000 (above all content)

**Success toast**:
```
┌─────────────────────────────────┐
│ ✓ Note saved successfully       │
└─────────────────────────────────┘
Duration: 4s, auto-dismiss
```

**Error toast**:
```
┌─────────────────────────────────┐
│ ⚠️ Failed to save note          │
│ [Retry]                        │
└─────────────────────────────────┘
Duration: 6s or manual dismiss
```

**Info toast**:
```
┌─────────────────────────────────┐
│ ℹ️ 5 notes archived             │
│ [Undo]                         │
└─────────────────────────────────┘
Duration: 3s or manual dismiss
```

---

## 8. Mobile-First Responsive Design

### 8.1 Breakpoints

**Define breakpoints from small-first**:

```css
/* Mobile (default) */
@media screen and (min-width: 640px) { /* Tablet small */ }
@media screen and (min-width: 768px) { /* Tablet */ }
@media screen and (min-width: 1024px) { /* Desktop small */ }
@media screen and (min-width: 1200px) { /* Desktop */ }
@media screen and (min-width: 1400px) { /* Desktop large */ }
```

### 8.2 Layout Reflow Guide

| Element | Mobile | Tablet | Desktop |
|---------|--------|--------|---------|
| Topbar | 56px, logo-only | 60px, logo + title | 68px, full nav |
| Sidebar | Hidden (drawer) | Collapsed (hamburger) | Fixed, 240px |
| Main grid | 1 column (full) | 2 columns | 3–4 columns |
| Hero height | 200px | 240px | 280px |
| Button width | Full (100%) | Inline if space | Inline |
| Modal width | 100% (with 12px margin) | 90% | 70% (max 700px) |

### 8.3 Touch Targets

**Minimum 48px × 48px per WCAG 2.1 Level AAA**

```
Button (mobile):
├─ Height: 48px min (typically 48–56px)
├─ Width: Full container width (minus padding)
└─ Padding: 12px 24px (vertically centered)

Icon button (mobile):
├─ Size: 48px × 48px
├─ Icon inside: 24px × 24px
└─ Tap target: Full 48px area (hit area includes padding)

Link in text (mobile):
├─ Min height: 44px (if standalone)
├─ Line-height: 1.5–2 (if inline)
└─ Extra bottom margin after text (8px) for spacing
```

### 8.4 Responsive Typography

```css
/* Mobile */
h1 { font-size: 1.75rem; line-height: 1.2; }
h2 { font-size: 1.4rem; line-height: 1.3; }
p { font-size: 0.95rem; line-height: 1.6; }

/* Tablet (768px+) */
@media (min-width: 768px) {
  h1 { font-size: 2rem; }
  h2 { font-size: 1.5rem; }
  p { font-size: 1rem; }
}

/* Desktop (1024px+) */
@media (min-width: 1024px) {
  h1 { font-size: 2.2rem; }
  h2 { font-size: 1.6rem; }
  p { font-size: 1.05rem; }
}
```

### 8.5 Responsive Images

**Rule**: Always use `max-width: 100%` and responsive images with srcset

```html
<img 
  src="diagram-400w.png"
  srcset="diagram-400w.png 400w,
          diagram-800w.png 800w,
          diagram-1200w.png 1200w"
  sizes="(max-width: 640px) 100vw,
         (max-width: 1024px) 90vw,
         1000px"
  alt="System architecture diagram"
/>
```

### 8.6 Viewport Optimization

```html
<meta name="viewport" 
      content="width=device-width, initial-scale=1.0, viewport-fit=cover, maximum-scale=5">
```

- `width=device-width`: Responsive width
- `initial-scale=1.0`: No initial zoom
- `viewport-fit=cover`: Notch support (iPhone)
- `maximum-scale=5`: Allow zoom for accessibility

---

## 9. Accessibility (WCAG 2.1 AA)

### 9.1 Keyboard Navigation

**Tab order**:
- Logical flow (left-to-right, top-to-bottom)
- Skip links on each page: `[Skip to main content]` (visible on focus)
- Focus indicators: 2px blue outline (minimum 2:1 contrast ratio)

**Focus trap** (modal):
- When modal opens, trap Tab key within modal
- Tab on last button → focus to first button (circular)
- Esc key closes modal

**Implementation** (pseudo-code):
```
On modal open:
  1. Store previous focus element
  2. Find all focusable elements in modal
  3. Add keydown listener for Tab
  4. If Tab on last element, move to first
  5. On Esc, close modal and restore focus

On modal close:
  1. Return focus to trigger button
```

### 9.2 Screen Reader Support

**ARIA labels** (for non-obvious elements):

```html
<!-- Icon button -->
<button aria-label="Delete note">🗑️</button>

<!-- Topbar navigation -->
<nav aria-label="Breadcrumb">
  <ol>
    <li><a href="/">Index</a></li>
    <li><a href="/research">Research</a></li>
    <li aria-current="page">Notes</li>
  </ol>
</nav>

<!-- Form field -->
<label for="note-title">Title <span aria-label="required">*</span></label>
<input id="note-title" required />

<!-- Region -->
<section aria-label="Recent activity">
  <!-- content -->
</section>

<!-- Live update -->
<div aria-live="polite" aria-atomic="true">
  Saving note...
</div>
```

**Semantic HTML**:
```html
<!-- Use instead of generic divs -->
<button> for clickable actions
<a href> for navigation
<form> for forms
<fieldset> for grouped form fields
<label> for form inputs
<header>, <nav>, <main>, <footer> for page structure
<article>, <section>, <aside> for content regions
```

### 9.3 Color Contrast

**Minimum ratios**:
- **4.5:1** for normal text on background
- **3:1** for large text (18px+ bold or 24px+)
- **3:1** for UI components (borders, buttons)

**Audit** (using tools):
- WebAIM Contrast Checker
- WAVE
- Lighthouse (built into DevTools)

### 9.4 Form Accessibility

```html
<!-- Correct pattern -->
<form>
  <fieldset>
    <legend>Create Research Note</legend>
    
    <label for="title">Title <span aria-label="required">*</span></label>
    <input id="title" 
           type="text" 
           required 
           aria-required="true"
           aria-describedby="title-hint" />
    <div id="title-hint" class="hint">Max 120 characters</div>
    
    <fieldset>
      <legend>Layer</legend>
      <input id="layer-0" type="radio" name="layer" value="0" />
      <label for="layer-0">Layer 0 (Qualification)</label>
      
      <input id="layer-2" type="radio" name="layer" value="2" />
      <label for="layer-2">Layer 2 (Signals)</label>
    </fieldset>
    
    <button type="submit">Save Note</button>
  </fieldset>
</form>
```

### 9.5 Focus Management

**On page load**: Focus on main content area or first interactive element
**On modal open**: Focus on close button or first form field
**On form submission**: 
- If error: Move focus to first error message
- If success: Show success toast and return focus to trigger button

**Implementation**:
```javascript
// Focus an element programmatically
element.focus({ preventScroll: true });

// Or use aria-label to announce focus change
const region = document.getElementById('main');
region.setAttribute('tabindex', '-1');
region.focus();
region.setAttribute('aria-label', 'Page content');
```

### 9.6 Motion & Animations

**Respect `prefers-reduced-motion`**:

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

**Avoid**: 
- Rapid blinking (> 3x/second)
- Parallax scrolling (disorienting)
- Auto-playing video/audio without user control

---

## 10. Error Handling & User Guidance

### 10.1 Error Message Hierarchy

**Level 1: Inline field errors** (validation during form completion)
```
Title *
[                              ]
⚠️ Title is required           ← Red text, clear guidance
```

**Level 2: Form-level summary** (after submit attempt)
```
┌─ Form Error Summary ─────────────────────┐
│ Please fix the following before saving:  │
│ • Title is required                      │
│ • Content must be at least 20 chars      │
│ • Please select a layer                  │
└──────────────────────────────────────────┘
```

**Level 3: Toast notification** (network/async errors)
```
┌────────────────────────────────┐
│ ⚠️ Failed to save note         │
│ Connection error. Retry?       │
│ [Retry] [Cancel]              │
└────────────────────────────────┘
```

**Level 4: Page-level error** (critical system failure)
```
┌────────────────────────────────────────┐
│                                        │
│           ⚠️ System Error              │
│                                        │
│    We encountered an unexpected        │
│    error. Our team has been            │
│    notified. Please try again in       │
│    a few minutes.                      │
│                                        │
│    Error code: 500                     │
│    [Reload Page] [Go Home]             │
│                                        │
└────────────────────────────────────────┘
```

### 10.2 Error Message Copy

**Good**:
- Specific ("Title must be at least 5 characters" vs "Invalid input")
- Actionable ("Enter a valid email address" vs "Email error")
- Tone: Professional but friendly ("Please select a category" vs "Category field empty")
- Avoid code/jargon ("Connection lost" vs "HTTP 503")

**Bad**:
- Generic ("Error")
- Blame-y ("You didn't fill out the form")
- Technical jargon ("NullPointerException in line 432")

### 10.3 Retry Mechanisms

**Pattern 1: Explicit retry button**
```
┌────────────────────────────────────┐
│ ⚠️ Failed to load research notes   │
│ [Retry] [Go to Dashboard]          │
└────────────────────────────────────┘
```

**Pattern 2: Auto-retry with exponential backoff**
```
Failed to load notes.
Retrying in 3 seconds... [Cancel]
```

Then:
```
Retrying in 2 seconds... [Cancel]
Retrying in 1 second... [Cancel]
✓ Loaded successfully
```

**Pattern 3: Graceful degradation**
```
Some data unavailable
┌────────────────────────────────┐
│ 🔍 Note 1: Macro Analysis     │
│ [Details unavailable]          │
│ Last updated: 5 days ago       │
├────────────────────────────────┤
│ 📊 Note 2: Signal Design      │
│ Full details loaded ✓          │
└────────────────────────────────┘
```

### 10.4 Validation Timing

**Real-time validation** (as user types):
- Debounce 500ms to avoid flickering
- Show hint-style messages, not errors
- Example: "Username is available" (green check)

**On-blur validation** (after user leaves field):
- More strict, shows errors
- Appropriate for required fields, format checks
- Helps reduce form anxiety

**On-submit validation** (before form submission):
- Final gate; prevents invalid submission
- Show summary of all errors (form level)
- Focus to first error

---

## 11. Component Library Reference

### 11.1 Reusable Component Patterns

**Card**:
- Border, shadow, rounded corners (10px)
- Hover: lift shadow, cursor pointer
- Padding: 20px (desktop), 16px (mobile)
- Use for: research notes, strategy summaries, metrics

**Modal**:
- Width: 70% (desktop), 90% (mobile), max 700px
- Centered both axes
- Backdrop: semi-transparent dark
- Close button: top-right corner or via Esc

**Topbar**:
- Sticky, height 68px (desktop) / 56px (mobile)
- Flex layout: [Brand] [Title] [Actions]
- Backdrop blur 12px
- Border-bottom: 1px, light gray

**Badge/Tag**:
- Padding: 4px 12px
- Border-radius: 20px (pill)
- Font-size: 0.8rem
- Use for: category indicators, status labels

**Button**:
- 36px height (default), 48px (large), 28px (small)
- Rounded corners: 10px
- 12px horizontal padding

**Input Field**:
- Height: 36px
- Padding: 10px 12px
- Border: 1px, light gray
- Focus: 2px blue border, light blue background tint
- Border-radius: 8px

---

## 12. Design Tokens & Constants

### 12.1 Color Palette

```css
:root {
  /* Primary */
  --primary: #1a73e8;           /* Brand blue */
  --primary-dark: #1557b0;      /* Darker blue */
  --primary-light: #e8f0fe;     /* Very light blue (bg) */
  
  /* Grays */
  --text: #1f2937;              /* Main text */
  --text-light: #6b7280;        /* Secondary text */
  --text-muted: #9ca3af;        /* Muted text */
  --bg: #f8faff;                /* Page background */
  --bg-card: #ffffff;           /* Card background */
  --border: #e2e8f0;            /* Border color */
  
  /* Semantic */
  --success: #10b981;           /* Green */
  --warning: #f59e0b;           /* Amber */
  --danger: #ef4444;            /* Red */
  
  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.1);
  --shadow-lg: 0 8px 30px rgba(0,0,0,0.12);
  
  /* Sizing */
  --radius: 10px;
  --radius-lg: 16px;
  --max-width: 1200px;
  
  /* Transitions */
  --transition: 0.3s ease;
}
```

### 12.2 Typography Scale

```css
/* Headings */
h1 { font-size: 2.2rem; font-weight: 800; line-height: 1.2; }
h2 { font-size: 1.6rem; font-weight: 700; line-height: 1.3; }
h3 { font-size: 1.3rem; font-weight: 700; line-height: 1.4; }
h4 { font-size: 1.1rem; font-weight: 600; line-height: 1.4; }

/* Body text */
p, .text-base { font-size: 1rem; font-weight: 400; line-height: 1.6; }
.text-small { font-size: 0.9rem; line-height: 1.5; }
.text-xs { font-size: 0.8rem; line-height: 1.4; }

/* Font family */
--font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
--font-mono: 'Courier New', monospace;
```

### 12.3 Spacing Scale

```css
:root {
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;
  --space-2xl: 32px;
  --space-3xl: 48px;
  --space-4xl: 64px;
}

/* Usage */
padding: var(--space-lg);       /* 16px */
margin-bottom: var(--space-xl); /* 24px */
gap: var(--space-md);           /* 12px */
```

---

## 13. Page-by-Page Flows & Wireframes

### 13.1 Index (Hub) Page Flow

```
User lands on index.html
├─ Topbar: Logo + "Scalable Brain" + Search toggle
├─ Hero Section
│  ├─ Eyebrow: "Quantitative Trading Platform"
│  ├─ Title: "Scalable Brain"
│  ├─ Subtitle: "Live trading + research hub"
│  └─ CTA buttons: [Explore Research] [View Docs]
├─ Quick Stats (4 cards in row)
│  ├─ Signal Accuracy (87.3%)
│  ├─ ML Confidence (91.2%)
│  ├─ Trades Executed (1,247)
│  └─ Monthly Return (+4.2%)
├─ Recent Activity (3–5 items)
│  ├─ Last Layer 4 run
│  ├─ Open alerts
│  └─ Recent trades
├─ Navigation Grid (6 cards)
│  ├─ Research Hub
│  ├─ Strategy Lab
│  ├─ Architecture
│  ├─ Data References
│  ├─ Execution Logs
│  └─ Documentation
└─ Footer: Links, version, copyright
```

### 13.2 Research Hub Flow

**Landing on research.html**:
```
User clicks "Research Hub" from index
│
├─ Topbar
│  ├─ Back link (to Index)
│  ├─ Title: "Research Hub"
│  ├─ Breadcrumb: Index / Research
│  └─ Search toggle
│
├─ Page Header
│  ├─ Title: "Research Notes"
│  └─ Subtitle: "Organize and track research findings"
│
├─ Controls Row
│  ├─ [✨ New Note] button
│  ├─ Search box (Ctrl+F)
│  ├─ [↓ Sort] dropdown
│  └─ [⚙️ Filter] toggle
│
├─ Filters Sidebar (visible on desktop, drawer on mobile)
│  ├─ Search box
│  ├─ Categories (checkboxes)
│  ├─ Layers (radio)
│  ├─ Date range (picker)
│  ├─ Tags (multi-select)
│  └─ [Clear All]
│
├─ Main Content Area
│  ├─ Applied filters (pills)
│  ├─ Results count: "24 research notes"
│  ├─ Card grid (3–4 columns desktop, 2 tablet, 1 mobile)
│  │  ├─ Card 1 [hover: lift shadow]
│  │  ├─ Card 2
│  │  └─ Card N
│  └─ Pagination / Load More
│
└─ Footer: Help, export, archive options
```

**Create new note flow**:
```
User presses Ctrl+K or clicks [✨ New Note]
│
├─ Modal opens (fade in + scale)
│  ├─ Title input [focused, placeholder: "Enter note title"]
│  ├─ Category dropdown
│  ├─ Layer radio group
│  ├─ Rich text editor
│  ├─ Tags multi-select
│  └─ [Cancel] [Save Draft] [Publish]
│
├─ Validation as user fills
│  └─ Real-time hint-style feedback
│
├─ On save
│  ├─ Submit button disables, shows spinner
│  ├─ Modal closes
│  ├─ Toast: "✓ Note created successfully"
│  └─ Grid updates (new card added)
│
└─ On cancel
   ├─ If no changes: Close immediately
   └─ If changes made: Warn "Discard draft?"
```

### 13.3 Dashboard / Overview Flow

**Landing on overview.html**:
```
User clicks "Overview" or "Dashboard" from navigation
│
├─ Topbar
│  ├─ Back link (if from research)
│  ├─ Title: "Dashboard"
│  └─ Breadcrumb: Index / Overview
│
├─ Hero Section
│  ├─ Eyebrow: "Your Trading System"
│  ├─ Title: "Scalable Brain Status"
│  ├─ Subtitle: "Real-time performance snapshot"
│  └─ CTA: [Explore Research] [View Docs]
│
├─ Stats Cards (4-column grid)
│  ├─ Signal Accuracy [87.3% ↑ +2.1%]
│  ├─ ML Confidence [91.2% ↓ -1.3%]
│  ├─ Trades Executed [1,247 ↑ +156]
│  └─ Monthly Return [+4.2% ↑ +1.8%]
│
├─ Recent Activity Section
│  ├─ Last Layer 4 run: 6h ago (48 trades)
│  ├─ Pending alerts: 3 (1 high)
│  ├─ Active strategies: 12
│  └─ [View All] links
│
├─ Quick Links Grid (2 columns on desktop, 1 mobile)
│  ├─ [→ View All Trades]
│  ├─ [→ View Alerts]
│  ├─ [→ Open Research Hub]
│  └─ [→ System Architecture]
│
└─ Footer: Last sync time, status indicator
```

---

## 14. Interaction Patterns Summary

### 14.1 CRUD Operations

**Create**:
- Trigger: Button in header (prominent) or Ctrl+K shortcut
- UI: Modal form with validation
- Feedback: Toast on success, inline errors on fail

**Read**:
- Trigger: Click card title, click "View" action button, or navigate via breadcrumb
- UI: Detail page (read-only, with edit/delete actions)
- Feedback: Skeleton loading on initial load

**Update**:
- Trigger: Click "Edit" button on detail page or card action menu
- UI: Modal form pre-filled with data
- Feedback: Toast on success, with undo option (5s window)

**Delete**:
- Trigger: Action menu ("More" > "Delete")
- UI: Confirmation modal ("Are you sure?")
- Feedback: Archive action (soft delete), undo toast (10s window)

### 14.2 Search & Filter Patterns

**Search** (in header):
- Real-time, debounced 300ms
- Searches: title, preview, tags, metadata
- Results update in main grid instantly
- Clear button appears once text entered

**Filter** (sidebar or drawer):
- Multi-select (category, tags)
- Radio buttons (layer, status)
- Date picker (range)
- "Clear All" button to reset
- Sticky "Apply" or auto-apply on change

**Results feedback**:
- "24 results" count shown
- If 0 results: Show empty state with filter suggestions
- Filters shown as removable pills above results

---

## 15. Accessibility Compliance Checklist

- [ ] All buttons have clear, descriptive labels
- [ ] All images have alt text
- [ ] Color not sole means of conveying information (use icons, text)
- [ ] Links have 4.5:1 contrast ratio minimum
- [ ] Focus indicators visible on all interactive elements
- [ ] Form labels associated with inputs (`for` attribute)
- [ ] Modal focus trap implemented
- [ ] Keyboard navigation works throughout site (Tab, Enter, Esc)
- [ ] ARIA live regions for async updates (toasts, loading)
- [ ] Form validation messages accessible to screen readers
- [ ] Videos/audio have captions (if applicable)
- [ ] Skip navigation link available
- [ ] Respects `prefers-reduced-motion` setting
- [ ] Text resize to 200% without loss of functionality
- [ ] Color contrast checked with WCAG tools

---

## 16. Performance & Loading Considerations

### 16.1 Performance Targets

- **First Contentful Paint (FCP)**: < 1.5s
- **Largest Contentful Paint (LCP)**: < 2.5s
- **Cumulative Layout Shift (CLS)**: < 0.1
- **Time to Interactive (TTI)**: < 3.5s

### 16.2 Optimization Strategies

**Images**:
- Use WebP with JPEG fallback
- Lazy-load below-the-fold images
- Responsive images with srcset

**Code splitting**:
- Load page-specific CSS/JS only when needed
- Defer non-critical JavaScript

**Caching**:
- Browser cache: 30 days for static assets
- Service worker: Cache research grid for offline fallback

**Skeleton loading**:
- Show structural placeholders while data loads
- Preferred over spinners (feels faster)

---

## 17. Design System Integration

### 17.1 Component Tokens Mapping

| Component | Design Token | Example |
|-----------|--------------|---------|
| Primary Button | --primary, --shadow-md | Blue button, lifted on hover |
| Card | --border, --shadow-md, --radius-lg | Research note card |
| Input | --border, --primary (focus), --text | Form field |
| Badge | --primary-light, --text-light, --radius | Category badge |
| Modal | --shadow-lg, --bg-card, --border | Create note modal |
| Toast | Semantic colors, --shadow-lg | Success/error notification |

### 17.2 Extending the Design System

**New pattern checklist**:
- [ ] Define token values (colors, sizes, shadows)
- [ ] Document component anatomy (parts, states)
- [ ] Establish interaction behavior (hover, focus, active)
- [ ] Create accessibility guidelines
- [ ] Add to component library docs
- [ ] Test at multiple breakpoints
- [ ] Validate color contrast (WCAG AA minimum)

---

## Conclusion

This UX architecture establishes a **consistent, accessible, and responsive** foundation for Scalable Brain's frontend. The navigation model enables researchers, operators, and architects to move fluidly between research, strategy, and system insights. Component patterns and interaction designs are grounded in enterprise UX best practices and accessibility standards (WCAG 2.1 AA).

**Next steps** for implementation:
1. Build component library (buttons, cards, modals, inputs)
2. Implement topbar/navigation across all pages
3. Redesign Research Hub with sidebar + card grid
4. Update Dashboard with hero + stats cards
5. Add keyboard shortcuts and focus management
6. Audit for accessibility (WAVE, Lighthouse)
7. Test responsive layout at all breakpoints
8. Collect user feedback and iterate

**Governance**:
- Review design changes against this document before implementation
- Update tokens/patterns when design evolves
- Maintain component library as source of truth
- Conduct quarterly accessibility audits

---

**Document prepared by**: Senior Frontend Architect  
**Scalable Brain Frontend Team**  
**May 7, 2026**
