# Scalable Brain Design System Specification
## Enterprise-Grade UI System v1.0 | Material Design 3 Compliant

---

## 1. DESIGN SYSTEM OVERVIEW

This specification defines a modern, enterprise-grade design system for Scalable Brain—a quantitative trading platform. It follows Google Material Design 3 principles with custom adaptations for financial data visualization and trading workflows.

**Core Design Philosophy:**
- **Clarity First**: Financial data requires precision and immediate comprehension
- **Micro-Interactions**: Feedback at every user action (empty states, loading, transitions)
- **Accessibility**: WCAG 2.1 AA compliance minimum (contrast, typography, focus states)
- **Performance**: CSS-only animations; no JavaScript dependencies for core interactions
- **Scalability**: Component-based architecture supporting 3-4 screen sizes

**Design Tokens:** All values are CSS variables for maintainability and theme switching.

---

## 2. COLOR PALETTE & TOKENS

### 2.1 Light Mode (Default)

#### Primary Colors (Core Brand)
```
--color-primary-0:        #001a4d    // Darkest (accessibility)
--color-primary-10:       #0d2d7a    // Dark emphasis
--color-primary-25:       #0f3fa1    // Deep shade
--color-primary-40:       #1557b0    // Primary Dark
--color-primary-50:       #1a73e8    // Primary Brand Color ⭐
--color-primary-60:       #3d87f5    // Primary Light
--color-primary-70:       #6ba3ff    // Secondary Light
--color-primary-80:       #9dc3ff    // Soft Light
--color-primary-90:       #c8d9ff    // Very Light
--color-primary-95:       #e8f0fe    // Lightest (backgrounds)
--color-primary-99:       #f8f9fe    // Near white
```

#### Secondary Colors (Data Visualization)
```
--color-secondary-40:     #0d8d7a    // Teal/Accent ⭐
--color-secondary-50:     #0fa89f    // Teal highlight
--color-secondary-60:     #33bfb0    // Teal light
--color-secondary-80:     #7dd4c6    // Teal very light
--color-secondary-90:     #b0e8e1    // Teal lightest
--color-secondary-95:     #d8f4f0    // Teal background
```

#### Tertiary Colors (Warnings, Alerts, Status)
```
--color-tertiary-40:      #b8860b    // Golden/Warning
--color-tertiary-50:      #f59e0b    // Warning ⭐
--color-tertiary-80:      #fcd34d    // Warning light
--color-tertiary-90:      #fef3c7    // Warning background
```

#### Semantic Colors
```
--color-success-40:       #0a7a46    // Dark green
--color-success-50:       #10b981    // Success ⭐
--color-success-80:       #86efac    // Success light
--color-success-90:       #dcfce7    // Success background

--color-error-40:         #a41e4e    // Dark red
--color-error-50:         #ef4444    // Error/Danger ⭐
--color-error-80:         #fca5a5    // Error light
--color-error-90:         #fee2e2    // Error background

--color-info-40:          #0369a1    // Dark cyan
--color-info-50:          #0ea5e9    // Info ⭐
--color-info-80:          #7dd3fc    // Info light
--color-info-90:          #cffafe    // Info background
```

#### Neutral Colors (Gray Scale)
```
--color-neutral-0:        #000000    // Pure black
--color-neutral-10:       #1a1a1a    // Near black (text emphasis)
--color-neutral-20:       #333333    // Dark gray
--color-neutral-30:       #4d4d4d    // Medium-dark gray
--color-neutral-40:       #666666    // Medium gray (muted text)
--color-neutral-50:       #808080    // Mid gray
--color-neutral-60:       #999999    // Light-mid gray
--color-neutral-70:       #b3b3b3    // Light gray
--color-neutral-80:       #cccccc    // Very light gray
--color-neutral-90:       #e6e6e6    // Almost white gray
--color-neutral-95:       #f2f2f2    // Off-white
--color-neutral-98:       #fafafa    // Near white
--color-neutral-99:       #ffffff    // Pure white
```

### 2.2 Dark Mode (Extended)

```
--color-primary-dark-bg:   #0f1d3d    // Surface variant
--color-primary-dark-fg:   #c8d9ff    // Text on dark
--color-neutral-dark-10:   #e6e6e6    // Light gray on dark
--color-neutral-dark-20:   #cccccc    // Medium gray on dark
--color-neutral-dark-90:   #1a1a1a    // Near black for dark surfaces
```

### 2.3 CSS Color Palette (Implementation)

```css
:root {
  /* PRIMARY PALETTE */
  --primary: #1a73e8;
  --primary-dark: #1557b0;
  --primary-light: #3d87f5;
  --primary-lighter: #c8d9ff;
  --primary-lightest: #e8f0fe;
  
  /* SECONDARY (ACCENT) */
  --secondary: #0d8d7a;
  --secondary-light: #33bfb0;
  --secondary-lighter: #b0e8e1;
  --secondary-lightest: #d8f4f0;
  
  /* SEMANTIC COLORS */
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
  --info: #0ea5e9;
  
  /* BACKGROUNDS */
  --bg-primary: #ffffff;
  --bg-secondary: #f8faff;
  --bg-tertiary: #f0f4f9;
  --bg-hover: #f5f7fb;
  --bg-active: #e8f0fe;
  
  /* TEXT */
  --text-primary: #1f2937;
  --text-secondary: #6b7280;
  --text-tertiary: #9ca3af;
  --text-disabled: #d1d5db;
  
  /* BORDERS & DIVIDERS */
  --border-light: #e2e8f0;
  --border-medium: #cbd5e0;
  --border-dark: #a0aec0;
  
  /* DARK MODE OVERRIDES */
  --dm-bg-primary: #121212;
  --dm-bg-secondary: #1e1e1e;
  --dm-bg-tertiary: #2d2d2d;
  --dm-text-primary: #ffffff;
  --dm-text-secondary: #b0b0b0;
  --dm-text-tertiary: #808080;
}

/* Dark Mode Toggle */
@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: var(--dm-bg-primary);
    --bg-secondary: var(--dm-bg-secondary);
    --text-primary: var(--dm-text-primary);
    --text-secondary: var(--dm-text-secondary);
    --primary-light: #7ba3ff;
    --primary-lighter: #4d73d1;
  }
}

body {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
}
```

---

## 3. TYPOGRAPHY SYSTEM

### 3.1 Font Stack

```
/* Display (Headlines) */
font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* Body & UI */
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;

/* Monospace (Code, Data) */
font-family: 'Fira Code', 'SF Mono', 'Monaco', monospace;
```

### 3.2 Type Scale (Modular Scale 1.125 = 8pt base grid)

| Name | Font Size | Line Height | Letter Spacing | Font Weight | Use Case |
|------|-----------|-------------|-----------------|------------|----------|
| **Display Large** | 57px | 64px | -0.25px | 400 | Hero sections, main page titles |
| **Display Medium** | 45px | 52px | 0px | 500 | Large section headers |
| **Display Small** | 36px | 44px | 0px | 400 | Page section titles |
| **Headline Large** | 32px | 40px | 0px | 700 | Modal titles, card headers |
| **Headline Medium** | 28px | 36px | 0px | 700 | Section headers |
| **Headline Small** | 24px | 32px | 0px | 700 | Subsection headers |
| **Title Large** | 22px | 28px | 0px | 700 | Card titles, table headers |
| **Title Medium** | 16px | 24px | 0.15px | 600 | Button text, labels |
| **Title Small** | 14px | 20px | 0.1px | 600 | Small headers, emphasized text |
| **Body Large** | 16px | 24px | 0.5px | 400 | Primary body text ⭐ |
| **Body Medium** | 14px | 20px | 0.25px | 400 | Secondary body text |
| **Body Small** | 12px | 16px | 0.4px | 400 | Tertiary text, captions |
| **Label Large** | 14px | 20px | 0.1px | 500 | Button labels, badges |
| **Label Medium** | 12px | 16px | 0.5px | 500 | Small labels, tags |
| **Label Small** | 11px | 16px | 0.5px | 500 | Micro labels, hints |

### 3.3 CSS Typography Classes

```css
/* Headings */
.text-display-large { font-size: 57px; line-height: 64px; letter-spacing: -0.25px; font-weight: 400; }
.text-display-medium { font-size: 45px; line-height: 52px; font-weight: 500; }
.text-headline-large { font-size: 32px; line-height: 40px; font-weight: 700; }
.text-headline-medium { font-size: 28px; line-height: 36px; font-weight: 700; }
.text-headline-small { font-size: 24px; line-height: 32px; font-weight: 700; }
.text-title-large { font-size: 22px; line-height: 28px; font-weight: 700; }
.text-title-medium { font-size: 16px; line-height: 24px; letter-spacing: 0.15px; font-weight: 600; }
.text-title-small { font-size: 14px; line-height: 20px; letter-spacing: 0.1px; font-weight: 600; }

/* Body Text */
.text-body-large { font-size: 16px; line-height: 24px; letter-spacing: 0.5px; }
.text-body-medium { font-size: 14px; line-height: 20px; letter-spacing: 0.25px; }
.text-body-small { font-size: 12px; line-height: 16px; letter-spacing: 0.4px; }

/* Labels */
.text-label-large { font-size: 14px; line-height: 20px; letter-spacing: 0.1px; font-weight: 500; }
.text-label-medium { font-size: 12px; line-height: 16px; letter-spacing: 0.5px; font-weight: 500; }
.text-label-small { font-size: 11px; line-height: 16px; letter-spacing: 0.5px; font-weight: 500; }
```

### 3.4 Text Hierarchy Rules

- **Primary Text**: `--text-primary` on `--bg-primary` (contrast ratio ≥ 7:1)
- **Secondary Text**: `--text-secondary` on `--bg-secondary` (contrast ratio ≥ 4.5:1)
- **Disabled Text**: `--text-disabled` with opacity 0.5
- **Links**: `--primary` (no underline by default; underline on hover)

---

## 4. SPACING & LAYOUT GRID

### 4.1 8pt Grid System

All spacing follows an 8pt baseline grid:

```css
:root {
  --spacing-0: 0;
  --spacing-1: 4px;    /* 0.5x grid unit */
  --spacing-2: 8px;    /* 1x grid unit ⭐ */
  --spacing-3: 12px;   /* 1.5x grid unit */
  --spacing-4: 16px;   /* 2x grid unit */
  --spacing-5: 20px;   /* 2.5x grid unit */
  --spacing-6: 24px;   /* 3x grid unit */
  --spacing-7: 28px;   /* 3.5x grid unit */
  --spacing-8: 32px;   /* 4x grid unit */
  --spacing-9: 36px;   /* 4.5x grid unit */
  --spacing-10: 40px;  /* 5x grid unit */
  --spacing-12: 48px;  /* 6x grid unit */
  --spacing-14: 56px;  /* 7x grid unit */
  --spacing-16: 64px;  /* 8x grid unit */
  --spacing-20: 80px;  /* 10x grid unit */
  --spacing-24: 96px;  /* 12x grid unit */
}
```

### 4.2 Layout Container Sizes

```css
:root {
  --layout-mobile: 375px;         /* Minimum viewport */
  --layout-tablet: 768px;         /* Medium viewport */
  --layout-desktop: 1024px;       /* Large viewport */
  --layout-wide: 1440px;          /* Ultra-wide */
  
  --content-max-width: 1200px;    /* Max content width */
  --sidebar-width: 280px;         /* Sidebar width */
  --gutter: 24px;                 /* Outer margin (responsive) */
}
```

### 4.3 Grid Layouts

**Desktop (1200px+):**
- 12-column grid with 24px gutters
- Sidebar: 280px (fixed) + Content: remaining
- Card layouts: 2-4 columns depending on content type

**Tablet (768px-1023px):**
- 8-column grid with 16px gutters
- Sidebar: collapsed or overlay
- Card layouts: 2 columns

**Mobile (375px-767px):**
- Single column layout
- Full width cards
- 16px outer margin

---

## 5. SHADOW & ELEVATION SYSTEM

Material Design 3 uses elevation levels (0-5) instead of arbitrary shadows.

### 5.1 Elevation Tokens

```css
:root {
  /* Elevation 0 (No shadow - flat) */
  --elevation-0: none;
  
  /* Elevation 1 (Subtle - cards, inputs) */
  --elevation-1: 0 1px 3px rgba(0, 0, 0, 0.12), 
                 0 1px 2px rgba(0, 0, 0, 0.24);
  
  /* Elevation 2 (Default - cards on hover, chips) */
  --elevation-2: 0 3px 6px rgba(0, 0, 0, 0.16), 
                 0 3px 6px rgba(0, 0, 0, 0.23);
  
  /* Elevation 3 (Medium - floating action buttons, raised buttons) */
  --elevation-3: 0 10px 20px rgba(0, 0, 0, 0.19), 
                 0 6px 6px rgba(0, 0, 0, 0.23);
  
  /* Elevation 4 (High - modals, menus) */
  --elevation-4: 0 15px 25px rgba(0, 0, 0, 0.15), 
                 0 5px 10px rgba(0, 0, 0, 0.05);
  
  /* Elevation 5 (Maximum - notifications, popovers) */
  --elevation-5: 0 20px 40px rgba(0, 0, 0, 0.30);
}

/* Usage Examples */
.card { box-shadow: var(--elevation-1); }
.card:hover { box-shadow: var(--elevation-2); }
.modal { box-shadow: var(--elevation-4); }
.popover { box-shadow: var(--elevation-5); }
```

### 5.2 Shadow Rules

- Use shadows to indicate depth and layering
- Avoid multiple shadows on the same element
- Dark mode: increase shadow opacity by 20-30%

---

## 6. BORDER RADIUS & SHAPE

Material Design 3 uses dynamic corner radius (not fixed):

```css
:root {
  /* Shape Corners */
  --radius-none: 0;           /* No radius */
  --radius-xs: 4px;           /* Extra small - chips, small buttons */
  --radius-sm: 8px;           /* Small - input fields, tabs */
  --radius-md: 12px;          /* Medium - cards, default ⭐ */
  --radius-lg: 16px;          /* Large - modals, section cards */
  --radius-xl: 20px;          /* Extra large - FAB, large buttons */
  --radius-full: 999px;       /* Full - pills, avatars, toggle switches */
}

/* Component-Specific */
.btn { border-radius: var(--radius-sm); }
.card { border-radius: var(--radius-md); }
.modal { border-radius: var(--radius-lg); }
.chip { border-radius: var(--radius-full); }
.avatar { border-radius: var(--radius-full); }
```

---

## 7. TRANSITIONS & ANIMATIONS

### 7.1 Animation Tokens

```css
:root {
  /* Easing Functions (Material Design 3) */
  --ease-standard: cubic-bezier(0.2, 0, 0.8, 1);           /* Standard motion */
  --ease-emphasized: cubic-bezier(0.05, 0.7, 0.1, 1);     /* Emphasized motion */
  --ease-decelerated: cubic-bezier(0, 0, 0.2, 1);         /* Decelerated motion */
  --ease-accelerated: cubic-bezier(0.4, 0, 1, 1);         /* Accelerated motion */
  
  /* Duration Tokens */
  --duration-short: 100ms;     /* Microinteractions */
  --duration-medium: 200ms;    /* Standard transitions */
  --duration-long: 300ms;      /* Complex animations */
  --duration-extra-long: 500ms;/* Page transitions */
}
```

### 7.2 Pre-Built Animations

```css
/* Fade In */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Slide In (from left) */
@keyframes slideInLeft {
  from { transform: translateX(-100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

/* Slide In (from top) */
@keyframes slideInTop {
  from { transform: translateY(-100%); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

/* Scale In */
@keyframes scaleIn {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

/* Bounce */
@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

/* Pulse (Loading state) */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Spin (Loading state) */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Shimmer (Skeleton loading) */
@keyframes shimmer {
  0% { background-position: -1000px 0; }
  100% { background-position: 1000px 0; }
}
```

### 7.3 Micro-Interaction Patterns

**Button Hover:**
```css
.btn {
  transition: all var(--duration-short) var(--ease-standard);
}
.btn:hover {
  transform: translateY(-2px);
  box-shadow: var(--elevation-2);
}
.btn:active {
  transform: translateY(0);
  box-shadow: var(--elevation-1);
}
```

**Card Hover:**
```css
.card {
  transition: all var(--duration-medium) var(--ease-standard);
}
.card:hover {
  box-shadow: var(--elevation-3);
  transform: translateY(-4px);
}
```

**Input Focus:**
```css
input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-lightest);
  transition: all var(--duration-short) var(--ease-standard);
}
```

---

## 8. COMPONENT LIBRARY SPECIFICATION

### 8.1 BUTTON COMPONENT

#### Variants

**1. Filled Button** (Primary Action)
- Background: `--primary`
- Text: `#ffffff`
- Min width: 88px, Height: 40px
- Padding: 10px 24px
- Border radius: `--radius-sm`
- States: Default, Hover, Active, Disabled, Loading

**2. Outlined Button** (Secondary Action)
- Background: `--bg-primary`
- Border: 1px solid `--primary`
- Text: `--primary`
- Same dimensions as Filled

**3. Tonal Button** (Tertiary Action)
- Background: `--primary-lightest`
- Text: `--primary-dark`
- Border: 0
- Same dimensions as Filled

**4. Text Button** (Minimal Action)
- Background: transparent
- Text: `--primary`
- No border
- Padding: 10px 16px
- No minimum width

**5. Elevated Button** (Prominent Secondary)
- Background: `--bg-primary`
- Box shadow: `var(--elevation-1)`
- Border: 0
- Text: `--primary`
- Same dimensions as Filled

#### State Styling

| State | Background | Text | Shadow | Cursor |
|-------|-----------|------|--------|--------|
| Default | Primary | White | Elevation-1 | pointer |
| Hover | Primary-dark | White | Elevation-2 | pointer |
| Active | Primary-dark | White | Elevation-1 | pointer |
| Disabled | Neutral-90 | Neutral-50 | None | not-allowed |
| Loading | Primary | White | Elevation-2 | default |

#### Icon Support
- Icons: 24px × 24px (left/right aligned)
- Gap: 8px between icon and text
- Icons inherit button text color

### 8.2 INPUT COMPONENT

#### Text Input
- Height: 40px (default), 36px (small), 48px (large)
- Padding: 10px 12px
- Border: 1px solid `--border-light`
- Border radius: `--radius-sm`
- Font size: 14px
- Line height: 20px

#### States

| State | Border | Background | Text | Focus |
|-------|--------|-----------|------|-------|
| Default | `--border-light` | `--bg-primary` | `--text-primary` | 3px solid focus ring |
| Hover | `--border-medium` | `--bg-hover` | `--text-primary` | N/A |
| Focus | `--primary` | `--bg-primary` | `--text-primary` | 3px primary ring |
| Disabled | `--border-light` | `--bg-tertiary` | `--text-disabled` | None |
| Error | `--error` | `--bg-primary` | `--text-primary` | 3px error ring |
| Success | `--success` | `--bg-primary` | `--text-primary` | 3px success ring |

#### Input Variants
- **Text Input**: Default text field
- **Number Input**: With spinner controls
- **Search Input**: With search icon + clear button
- **Password Input**: With show/hide toggle
- **Textarea**: Multi-line, min-height: 100px
- **Select**: Dropdown field with options

#### Label & Helper Text
- Label: `--text-primary`, 14px, 600 weight, 6px margin-bottom
- Helper text: `--text-tertiary`, 12px, below input
- Error text: `--error`, 12px, appears below input
- Character count: `--text-tertiary`, 12px, right-aligned

### 8.3 CARD COMPONENT

#### Base Card
- Background: `--bg-primary`
- Border: 1px solid `--border-light`
- Border radius: `--radius-md`
- Padding: 24px
- Box shadow: `var(--elevation-1)`
- Transition: all 200ms

#### Card Variants
1. **Elevated Card**: Shadow `--elevation-2`, interactive hover
2. **Filled Card**: Subtle background `--bg-tertiary`, border 0
3. **Outlined Card**: Thicker border `--border-medium`, no shadow
4. **Interactive Card**: Changes on hover (lift, shadow increase)

#### Card Parts
- **Card Header**: Padding 20px 24px, border-bottom 1px `--border-light`
- **Card Title**: 20px, 700 weight, `--text-primary`
- **Card Subtitle**: 14px, `--text-secondary`, margin-top 4px
- **Card Body**: Padding 24px, default spacing
- **Card Footer**: Padding 16px 24px, border-top 1px `--border-light`

#### Card with Image
- Image top-positioned, no margin
- Image height: 200px (responsive 16:9 aspect)
- Image border-radius: top corners of card

### 8.4 MODAL COMPONENT

#### Modal Overlay
- Background: `rgba(0, 0, 0, 0.50)` with backdrop blur (12px)
- Transition: fadeIn 300ms
- Z-index: 1000+
- Dismissable via overlay click (option)

#### Modal Dialog
- Background: `--bg-primary`
- Border radius: `--radius-lg`
- Box shadow: `var(--elevation-4)`
- Max width: 600px (responsive)
- Width: 90% on mobile
- Max height: 90vh (scrollable content)
- Animation: scaleIn 300ms + fadeIn

#### Modal Parts
- **Header**: Padding 24px, border-bottom 1px `--border-light`, title 24px 700 weight
- **Close Button**: 24px × 24px icon button, top-right positioned, hover opacity 0.7
- **Body**: Padding 24px, scrollable if needed
- **Footer**: Padding 16px 24px, border-top 1px `--border-light`, button alignment flex-end

#### Modal Animations
- **Open**: scaleIn (0.95 → 1.0) + fadeIn (0 → 1), 300ms
- **Close**: scaleOut (1.0 → 0.95) + fadeOut (1 → 0), 200ms
- **Backdrop**: fadeIn 300ms

### 8.5 CHIP COMPONENT

#### Base Chip
- Height: 32px
- Padding: 6px 12px (no icon), 4px 8px (with icon)
- Border radius: `--radius-full`
- Font size: 14px (label-medium)
- Display: inline-flex, align-items center, gap 4px

#### Chip Variants
1. **Assist Chip**: Background `--bg-tertiary`, border 1px `--border-light`, text `--text-primary`
2. **Filter Chip**: Background `--bg-tertiary` (default), `--primary-lightest` (selected)
3. **Input Chip**: With close icon, removable
4. **Suggestion Chip**: Background `--primary-lightest`, text `--primary`

#### Chip States
- Default: solid background, `--elevation-0`
- Hover: background darken 5%, cursor pointer
- Active: background `--primary`, text white
- Disabled: opacity 0.5, cursor not-allowed

#### Chip Parts
- **Icon** (left): 18px × 18px, margin-right 4px
- **Label**: 14px, no wrap
- **Close Icon** (right): 18px × 18px, clickable, margin-left 4px

### 8.6 BADGE COMPONENT

#### Badge Styles
- **Filled Badge**: Background `--primary`, text white, 12px font
- **Outlined Badge**: Border 1px `--primary`, background transparent, text `--primary`
- **Status Badge**: 8px circle indicator (no text)

#### Badge Sizes
- **Small**: 6px × 20px padding
- **Medium**: 8px × 12px padding (default)
- **Large**: 10px × 16px padding

#### Badge Positioning
- Top-right (default): `position: absolute; top: -4px; right: -4px;`
- Custom positions via utility classes

### 8.7 NAVIGATION PATTERNS

#### Top Navigation Bar
- Height: 64px
- Background: `--bg-primary`
- Border-bottom: 1px `--border-light`
- Sticky positioning: top 0, z-index 100
- Supports: Logo, navigation items, search, user menu

#### Tab Navigation
- Tab height: 48px
- Tab padding: 12px 16px
- Border-bottom: 3px (active tab only)
- Active tab color: `--primary`
- Inactive tab color: `--text-secondary`
- Animated underline: 200ms slide transition

#### Breadcrumb Navigation
- Separator: "/" or ">"
- Item spacing: 8px between items
- Active breadcrumb: `--text-primary` 600 weight
- Inactive breadcrumb: `--text-secondary`
- Links: underline on hover

#### Side Navigation
- Width: 280px (desktop), collapsible to 64px
- Background: `--bg-primary`
- Border-right: 1px `--border-light`
- Items: 48px height, padding 12px 16px
- Active item: `--primary-lightest` background
- Icon + label layout

#### Bottom Navigation (Mobile)
- Height: 56px
- Background: `--bg-primary`
- Border-top: 1px `--border-light`
- Max 5 items
- Icon (24px) + label (12px)
- Active: `--primary` text + icon

### 8.8 LOADING & EMPTY STATES

#### Spinner/Loading Indicator
```css
.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid --border-light;
  border-top-color: --primary;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Size variants */
.spinner-sm { width: 24px; height: 24px; }
.spinner-lg { width: 56px; height: 56px; }
```

#### Skeleton Loading
- Base: `--bg-tertiary` with shimmer animation
- Height/width: match target element dimensions
- Border radius: match target element
- Animation: shimmer 2s infinite

#### Empty State Pattern
- Icon: 64px × 64px, opacity 0.4, margin-bottom 16px
- Headline: 20px 700 weight, margin-bottom 8px
- Description: 14px `--text-secondary`, margin-bottom 24px
- Action Button: centered, optional
- Container: min-height 300px, flex centering, text-align center

#### Error State Pattern
- Icon: Warning/error icon (red), 64px
- Headline: "Something went wrong", 20px 700 weight
- Error message: 14px `--text-secondary`, max 2 lines
- Actions: Retry button + Go back link
- Optional: Error code (12px mono, `--text-tertiary`)

### 8.9 FORM COMPONENTS

#### Checkbox
- Size: 20px × 20px
- Border: 2px solid `--border-medium`
- Border radius: 2px
- Checked: Background `--primary`, white checkmark
- Disabled: opacity 0.5

#### Radio Button
- Size: 20px × 20px
- Border: 2px solid `--border-medium`
- Border radius: 50%
- Checked: Border 4px `--primary`, inner circle 4px `--primary`

#### Toggle Switch
- Width: 52px, Height: 32px
- Border radius: 16px
- Off: `--border-medium` border, gray thumb
- On: `--primary` background, white thumb
- Animation: translateX 200ms

#### Select/Dropdown
- Height: 40px
- Styling: same as text input
- Dropdown menu: positioned below, `--elevation-3`, max-height 300px scrollable
- Options: 40px height, 12px 16px padding, hover `--bg-hover`
- Selected option: highlight `--primary-lightest`

---

## 9. LAYOUT PATTERNS & GRIDS

### 9.1 Page Layout Template

```
┌─────────────────────────────────────┐
│  TOP NAVIGATION BAR (64px)          │ ← Sticky, elevation-2
├─────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────────┐ │
│ │   SIDEBAR   │ │    MAIN CONTENT │ │
│ │  (280px)    │ │    (responsive) │ │
│ │             │ │                 │ │
│ │  Nav Items  │ │  Page Header    │
│ │  (48px h)   │ │  (40-60px pad)  │
│ │             │ │                 │
│ │  ────────   │ │  ┌─────────────┐│
│ │             │ │  │   CARDS    ││
│ │             │ │  │  Grid: 2-4 ││
│ │             │ │  │  columns   ││
│ │             │ │  └─────────────┘│
│ │             │ │                 │
│ └─────────────┘ └─────────────────┘
├─────────────────────────────────────┤
│  FOOTER (80px)                      │
└─────────────────────────────────────┘
```

### 9.2 Content Area Grid Layouts

**Dashboard Grid (4 columns)**
```css
.grid-dashboard {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  
  @media (max-width: 1200px) {
    grid-template-columns: repeat(3, 1fr);
  }
  
  @media (max-width: 768px) {
    grid-template-columns: repeat(2, 1fr);
  }
  
  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
}
```

**Card Grid (Variable)**
```css
.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 24px;
}
```

**Data Table Container**
```css
.table-container {
  background: --bg-primary;
  border: 1px solid --border-light;
  border-radius: --radius-md;
  overflow: hidden;
  
  table {
    width: 100%;
    border-collapse: collapse;
  }
  
  thead {
    background: --bg-tertiary;
    border-bottom: 1px solid --border-light;
  }
  
  th {
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    color: --text-secondary;
  }
  
  td {
    padding: 12px 16px;
    border-bottom: 1px solid --border-light;
    color: --text-primary;
  }
  
  tr:hover {
    background: --bg-hover;
  }
}
```

### 9.3 Common Page Sections

**Page Header**
```css
.page-header {
  padding: 40px 0;
  margin-bottom: 40px;
  border-bottom: 1px solid --border-light;
  
  h1 {
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 8px;
  }
  
  .subtitle {
    font-size: 16px;
    color: --text-secondary;
    max-width: 600px;
  }
}
```

**Section Header**
```css
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  gap: 24px;
  
  h2 {
    font-size: 24px;
    font-weight: 700;
  }
  
  .actions {
    display: flex;
    gap: 12px;
  }
}
```

---

## 10. ACCESSIBILITY SPECIFICATIONS

### 10.1 WCAG 2.1 AA Compliance

**Color Contrast Ratios:**
- Large text (18px+/14px bold+): 3:1 minimum
- Normal text: 4.5:1 minimum
- Graphics/UI components: 3:1 minimum
- Focus indicators: 3:1 minimum

**Focus Management:**
- All interactive elements must have visible focus indicator
- Focus outline: 2px solid `--primary` or equivalent
- Focus outline offset: 2px
- Tab order follows logical flow
- Focus trap in modals

**Text & Typography:**
- Minimum font size: 12px (body text)
- Line height: minimum 1.5 (1.6 recommended)
- Letter spacing: minimum 0.12× font size
- Text alignment: left-aligned (LTR), no justified text

**Motion & Animation:**
- Respect `prefers-reduced-motion` media query
- All animations have duration ≤ 3 seconds
- No auto-playing videos/animations
- No flashing content >3 Hz

**Form Accessibility:**
- All inputs require associated labels
- Error messages linked to inputs via `aria-describedby`
- Required fields marked: `<abbr title="required">*</abbr>`
- Clear error messaging in plain language

### 10.2 ARIA Attributes

```html
<!-- Buttons -->
<button aria-label="Close dialog">✕</button>

<!-- Form inputs -->
<input id="email" type="email" aria-describedby="email-hint">
<small id="email-hint">Enter your email address</small>

<!-- Required fields -->
<input aria-required="true" />

<!-- Loading states -->
<div aria-busy="true" aria-label="Loading..."></div>

<!-- Disabled state -->
<button disabled aria-disabled="true">Submit</button>

<!-- Expandable sections -->
<button aria-expanded="false" aria-controls="menu-items">Menu</button>
<ul id="menu-items" hidden>...</ul>

<!-- Alerts -->
<div role="alert" aria-live="assertive">Error message</div>

<!-- Live regions -->
<div aria-live="polite" aria-atomic="true"></div>
```

### 10.3 Keyboard Navigation

- Tab: Move forward through focusable elements
- Shift+Tab: Move backward
- Enter: Activate button, submit form
- Space: Toggle checkbox/switch, activate button
- Escape: Close modal, collapse menu
- Arrow keys: Navigate tabs, select options, move focus in lists

---

## 11. RESPONSIVE DESIGN BREAKPOINTS

### 11.1 Breakpoint Strategy

```css
/* Mobile First Approach */
@media (min-width: 375px) { /* Mobile */
  --gutter: 16px;
  --layout: single-column;
}

@media (min-width: 768px) { /* Tablet */
  --gutter: 20px;
  --layout: two-column;
  --sidebar: visible;
}

@media (min-width: 1024px) { /* Desktop */
  --gutter: 24px;
  --layout: three-plus-column;
  --sidebar: 280px;
}

@media (min-width: 1440px) { /* Wide Desktop */
  --gutter: 32px;
  --max-width: 1440px;
}

/* Orientation-specific */
@media (orientation: landscape) and (max-height: 500px) {
  /* Compact layouts for small landscape screens */
}
```

### 11.2 Component Responsiveness

**Cards**
- Desktop: 4 columns (300px each)
- Tablet: 2 columns
- Mobile: 1 column (full width)

**Sidebar**
- Desktop: 280px fixed
- Tablet: 64px collapse/overlay toggle
- Mobile: Overlay hamburger menu

**Navigation**
- Desktop: Top bar + sidebar
- Tablet: Top bar + hamburger
- Mobile: Bottom tab navigation

**Modals**
- Desktop: max-width 600px centered
- Tablet: max-width 90vw
- Mobile: full screen with 16px padding

---

## 12. DARK MODE IMPLEMENTATION

### 12.1 Dark Mode Color Mapping

```css
@media (prefers-color-scheme: dark) {
  :root {
    /* Surface Colors */
    --bg-primary: #121212;      /* Black surface */
    --bg-secondary: #1e1e1e;    /* Elevated surface */
    --bg-tertiary: #2d2d2d;     /* Card surface */
    --bg-hover: #383838;        /* Hover state */
    --bg-active: #3f3f3f;       /* Active state */
    
    /* Text Colors */
    --text-primary: #ffffff;     /* Primary text */
    --text-secondary: #b0b0b0;   /* Secondary text */
    --text-tertiary: #808080;    /* Tertiary text */
    --text-disabled: #5a5a5a;    /* Disabled text */
    
    /* Borders */
    --border-light: #383838;     /* Light border */
    --border-medium: #454545;    /* Medium border */
    --border-dark: #5a5a5a;      /* Dark border */
    
    /* Component Adjustments */
    --primary-light: #7ba3ff;
    --primary-lighter: #4d73d1;
    --shadow-opacity: 0.3;       /* Increase shadow opacity */
  }
}

/* System preference toggle */
html[data-theme="dark"] {
  /* Apply dark mode styles */
}

html[data-theme="light"] {
  /* Apply light mode styles */
}
```

### 12.2 Dark Mode Component Adjustments

**Cards**
- Remove box shadow or reduce opacity by 50%
- Increase border opacity for visibility
- Text contrast maintained at 4.5:1+

**Buttons**
- Filled buttons: lighter background on hover
- Outlined buttons: lighter border/text on dark surfaces
- Elevated buttons: higher shadow opacity

**Inputs**
- Border: lighter color for visibility
- Background: `--bg-tertiary` (not pure black)
- Focus ring: adjust color for contrast

**Charts/Data Visualization**
- Grid lines: lighter opacity
- Axis labels: `--text-secondary`
- Series colors: adjusted for readability

---

## 13. MICRO-INTERACTION SPECIFICATIONS

### 13.1 Button Interactions

**Filled Button Flow**
1. **Idle**: Normal appearance, cursor: pointer
2. **Hover**: Lift +2px, shadow increase, icon scale 105%
3. **Press**: Lift 0px (flat), shadow reduce
4. **Focus**: Add focus ring outline, 2px offset
5. **Disabled**: Opacity 0.5, cursor: not-allowed, no interactions

**Interaction Timing:**
- Hover transition: 200ms
- Press feedback: 100ms
- Release: 150ms back to normal

### 13.2 Form Input Interactions

**Text Input Focus Flow**
1. **Idle**: Border `--border-light`, text `--text-primary`
2. **Hover**: Border `--border-medium`, background `--bg-hover`
3. **Focus**: Border `--primary`, 3px focus ring `--primary-lightest`, cursor inside
4. **Error**: Border `--error`, ring `--error` with 0.2 alpha
5. **Success**: Border `--success`, checkmark icon appears
6. **Filled**: Border `--border-medium`, label floats (if floating)

**Validation Feedback:**
- Character count: Show as user types
- Password strength: Visual indicator bar
- Email validation: Check icon appears on blur
- Error message: Slide down animation 200ms

### 13.3 Card Interactions

**Card Hover**
1. Box shadow: `--elevation-1` → `--elevation-3` (200ms ease)
2. Transform: Y offset 0px → -4px (200ms ease)
3. Border: subtle color shift (optional)
4. No cursor change unless card is clickable

### 13.4 Loading State Indicators

**Spinner Animation**
- Duration: 1s (one rotation)
- Easing: linear (continuous)
- Size: 40px (default), scalable
- Color: `--primary`
- Accessibility: `aria-busy="true" aria-label="Loading..."`

**Skeleton Loading**
- Placeholder background: `--bg-tertiary`
- Shimmer effect: left-to-right sweep every 2s
- Maintains layout integrity (no CLS)
- Auto-replaces with real content when loaded

**Progress Bar**
- Height: 4px (subtle)
- Duration: 0-100% animated (variable)
- Color: `--primary`
- Background: `--bg-tertiary`
- Optional: Stripes pattern with animation

### 13.5 Notification/Toast Interactions

**Toast Appearance**
- Slide in from bottom-right: 300ms scaleIn + slideInLeft
- Auto-dismiss after 5s
- Dismissed: slide out + fade 200ms
- Stacking: multiple toasts cascade upward

**Toast States**
- Success: Green background, checkmark icon
- Error: Red background, X icon
- Warning: Yellow background, alert icon
- Info: Blue background, info icon

---

## 14. DATA VISUALIZATION CONSIDERATIONS

### 14.1 Chart Component Integration

**Chart Container**
- Background: `--bg-primary`
- Border: 1px `--border-light`
- Border radius: `--radius-md`
- Padding: 24px
- Responsive: use container queries for sizing

**Chart Styling**
- Axis labels: `--text-secondary`, 12px
- Grid lines: `--border-light`, 0.5px, dashed
- Tooltips: Dark background (`--bg-secondary`), white text, `--elevation-4`
- Legend: 14px labels, inline or side-positioned

**Chart Series Colors**
- Series 1 (Primary): `--primary`
- Series 2 (Secondary): `--secondary`
- Series 3: `--success`
- Series 4: `--warning`
- Series 5: `--error`
- Additional: Generated from color palette

### 14.2 Table Specifications

**Table Header**
- Background: `--bg-tertiary`
- Text: `--text-secondary`, 12px uppercase
- Padding: 12px 16px
- Sort indicators: Chevron icon (12px)
- Sortable columns: cursor pointer, hover highlight

**Table Row**
- Height: 48px
- Padding: 12px 16px per cell
- Borders: 1px bottom `--border-light`
- Striped (optional): Even rows `--bg-hover`

**Table Interactions**
- Hover: Row background `--bg-hover`
- Selected: Row background `--primary-lightest`
- Clickable: Cursor pointer, highlight on hover
- Sortable: Chevron direction indicates order

---

## 15. COMPONENT INTERACTION MATRIX

| Component | Hover | Active | Focus | Disabled | Loading |
|-----------|-------|--------|-------|----------|---------|
| Button | Lift +2px, shadow ↑ | Flatten, shadow ↓ | Focus ring | Opacity 0.5 | Spinner icon |
| Input | Border color ↑ | Border primary | Focus ring | Opacity 0.5 | Spinner indicator |
| Card | Shadow ↑, lift -4px | N/A | Focus ring (if link) | Opacity 0.5 | Skeleton overlay |
| Chip | Bg color ↑ | Bg primary | Focus ring | Opacity 0.5 | N/A |
| Tab | Underline reveal | Underline solid | Focus ring | Opacity 0.5 | N/A |
| Checkbox | Border ↑ | Check appear | Focus ring | Opacity 0.5 | N/A |
| Toggle | N/A | State flip | Focus ring | Opacity 0.5 | N/A |

---

## 16. IMPLEMENTATION GUIDELINES

### 16.1 CSS Variable Usage

All components must use CSS variables for:
- Colors (primary, secondary, semantic)
- Spacing (8pt grid multiples)
- Typography (size, weight, line-height)
- Shadows (elevation levels)
- Border radius (shape tokens)
- Transitions (duration, easing)

### 16.2 Component Composition Rules

1. **Base Component**: Unstyled HTML element (e.g., `<button>`)
2. **Component Class**: Applies default styling (e.g., `.btn`)
3. **Variant Class**: Overrides specific aspects (e.g., `.btn-primary`, `.btn-outlined`)
4. **Size Class**: Adjusts dimensions (e.g., `.btn-sm`, `.btn-lg`)
5. **State Class**: Reflects interaction state (e.g., `.is-loading`, `.is-disabled`)

```html
<button class="btn btn-primary btn-lg is-loading">
  <span class="spinner"></span> Loading...
</button>
```

### 16.3 Dark Mode Implementation Patterns

```css
/* Pattern 1: Media Query */
@media (prefers-color-scheme: dark) {
  :root { --bg-primary: #121212; }
}

/* Pattern 2: Data Attribute */
html[data-theme="dark"] { --bg-primary: #121212; }

/* Pattern 3: Class-Based */
body.dark-mode { --bg-primary: #121212; }
```

**Recommended:** Combine Pattern 1 (system preference) + Pattern 3 (manual override)

### 16.4 Animation Best Practices

- Default duration: 200ms (micro-interactions)
- Complex animations: 300-500ms maximum
- Easing: Use `--ease-standard` by default
- Respect `prefers-reduced-motion: reduce`
- Test on low-end devices for performance

### 16.5 Responsive Design Patterns

```css
/* Mobile-First Approach */
.card { grid-template-columns: 1fr; }

@media (min-width: 768px) {
  .card { grid-template-columns: repeat(2, 1fr); }
}

@media (min-width: 1024px) {
  .card { grid-template-columns: repeat(3, 1fr); }
}
```

---

## 17. DESIGN SYSTEM TOKENS SUMMARY

### 17.1 Quick Reference Card

**Colors:**
- Primary: `--primary` (#1a73e8)
- Secondary: `--secondary` (#0d8d7a)
- Success: `--success` (#10b981)
- Warning: `--warning` (#f59e0b)
- Error: `--error` (#ef4444)

**Spacing:**
- Base unit: 8px
- Common: 8px, 12px, 16px, 24px, 32px

**Typography:**
- Body: 16px, 1.6 line-height
- Headings: 700 weight, -0.2px letter spacing
- Mono: 'Fira Code', 14px

**Shadows:**
- Default: `var(--elevation-1)`
- Hover: `var(--elevation-2)`
- Modal: `var(--elevation-4)`

**Radius:**
- Default: 12px
- Compact: 8px
- Full: 999px

**Duration:**
- Micro: 100ms
- Standard: 200ms
- Complex: 300ms

---

## 18. MIGRATION & ADOPTION ROADMAP

### Phase 1 (Week 1-2): Foundation
- Implement CSS variables and theme tokens
- Create base component styles
- Set up dark mode support

### Phase 2 (Week 3-4): Components
- Build button, input, card components
- Implement form components
- Create navigation patterns

### Phase 3 (Week 5-6): Layout & Pages
- Implement page layouts with sidebar
- Create responsive grids
- Build data table component

### Phase 4 (Week 7-8): Polish & Testing
- Add micro-interactions
- Test accessibility (WCAG 2.1 AA)
- Performance optimization
- Cross-browser testing

### Phase 5 (Ongoing): Documentation
- Component usage guide
- Accessibility checklist
- Code examples
- Design tokens export (JSON/CSS)

---

## 19. DESIGN TOKENS EXPORT

All tokens are available in multiple formats:
- **CSS**: Native CSS variables in stylesheet
- **JSON**: Machine-readable token structure
- **Design Tools**: Figma tokens plugin integration
- **Documentation**: Interactive token browser

---

## 20. APPENDIX: REFERENCE MATERIALS

### Color Palette Visual Reference
```
PRIMARY (Blue)        SECONDARY (Teal)     SEMANTICS
#1a73e8 ■■■          #0d8d7a ■■■         Success: #10b981 ■■■
#3d87f5 ■■■          #33bfb0 ■■■         Warning: #f59e0b ■■■
#c8d9ff ■■■          #b0e8e1 ■■■         Error:   #ef4444 ■■■
#e8f0fe ■■■          #d8f4f0 ■■■         Info:    #0ea5e9 ■■■

NEUTRALS (Gray)
#000000 ■ #1a1a1a ■ #333333 ■ #666666 ■ #999999 ■ #cccccc ■ #e6e6e6 ■ #ffffff ■
```

### Spacing Scale Visual
```
--spacing-2: |----| 8px
--spacing-3: |------| 12px
--spacing-4: |--------| 16px
--spacing-6: |------------| 24px
--spacing-8: |----------------| 32px
```

### Typography Scale Visual
```
Display Large    ██████████████████████████████ 57px
Display Medium   ███████████████████████████ 45px
Headline Large   ████████████████████████ 32px
Title Large      ██████████████████ 22px
Body Large       ████████████████ 16px (⭐ Base)
Body Medium      ██████████████ 14px
Label Medium     ████████████ 12px
```

---

## END OF DESIGN SYSTEM SPECIFICATION

**Document Version:** 1.0  
**Last Updated:** May 2026  
**Status:** Ready for Implementation  
**Compliance:** Material Design 3, WCAG 2.1 AA, Responsive Design Best Practices

---
