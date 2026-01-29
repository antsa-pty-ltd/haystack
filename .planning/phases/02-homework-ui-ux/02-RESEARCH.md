# Phase 02: Homework Assignment UI/UX Improvements - Research

**Researched:** 2026-01-29
**Domain:** React web application UI/UX patterns, three-panel layouts, Ant Design 5
**Confidence:** HIGH

## Summary

This phase focuses on redesigning the homework assignment interface in the web practitioner portal (React + Redux + TypeScript) to improve usability through a three-panel master-detail layout, enhanced visual feedback, and better organization. The current implementation at `/web/src/pages/homework/Homework.tsx` uses a two-column layout with collapsible categories but lacks consistent visual feedback and clear empty states.

**Current State Analysis:**
- Two-panel layout exists (categories | homework list)
- Collapsible categories already implemented with Ant Design Collapse
- Drag-and-drop uses react-beautiful-dnd (deprecated library)
- Search/filter functionality exists with debouncing (1000ms delay)
- Mobile responsive with slide-in panels
- SCSS with BEM methodology for styling
- Playwright configured for E2E testing

**Key Research Findings:**
- React-beautiful-dnd is deprecated; migration to dnd-kit recommended for future-proofing
- WCAG 2.2 requires alternative input methods for drag-and-drop (keyboard, buttons)
- Three-panel layouts follow master-detail-preview pattern with responsive breakpoints
- Ant Design 5 provides robust component library with consistent design system
- Modern hover states require 0.2s-0.4s transitions with GPU-accelerated properties

**Primary recommendation:** Enhance existing layout with improved visual feedback, empty states, and accessibility features while preparing for eventual migration from react-beautiful-dnd to dnd-kit.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.2.0 | UI framework | Component-based architecture, hooks ecosystem |
| Ant Design | 5.3.2 | UI component library | Enterprise-grade components, consistent design system |
| SCSS | 1.53.0 | CSS preprocessor | BEM methodology support, variables, nesting |
| TypeScript | 4.4.2 | Type safety | Interface definitions, compile-time safety |
| Redux Toolkit | 1.9.3 | State management | Already integrated, predictable state updates |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| react-beautiful-dnd | 13.1.1 | Drag and drop (current) | EXISTING - no changes for this phase |
| lodash/debounce | 4.17.21 | Input debouncing | Search optimization, already in use |
| react-infinite-scroll-component | 6.1.0 | Infinite scrolling | Large homework lists, already in use |
| classnames | - | Conditional CSS classes | Dynamic BEM modifiers |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-beautiful-dnd | dnd-kit 18.0+ | More modern, better accessibility, but requires migration effort |
| react-beautiful-dnd | pragmatic-drag-and-drop | Atlassian's replacement, framework-agnostic, but different API |
| Ant Design 5 | MUI 6.x | Material Design system, but inconsistent with existing codebase |
| SCSS + BEM | CSS Modules | Scoped styles, but would break existing patterns |

**Installation:**
```bash
# No new libraries needed for Phase 02
# Existing dependencies sufficient
cd web
npm install # Ensures all current deps installed
```

## Architecture Patterns

### Recommended Project Structure
```
web/src/pages/homework/
├── Homework.tsx                    # Main page with three-panel layout
├── Homework.scss                   # Styles following BEM
├── components/
│   ├── homework-list/              # Middle panel: homework items list
│   ├── homework-detail/            # Right panel: preview/details
│   ├── homework-task-row/          # Individual homework row
│   └── new-topic-modal/            # Topic creation modal
└── BulkAssignHomework.tsx          # Separate bulk assignment page
```

### Pattern 1: Three-Panel Master-Detail Layout
**What:** Categories (master) → List (detail) → Preview (extended detail)
**When to use:** Content navigation with hierarchical relationships
**Example:**
```typescript
// Current two-panel grid
.HomeworkPage__grid {
  display: grid;
  grid-template-columns: 380px 1fr; // categories | list
  gap: 32px;
}

// Enhanced three-panel grid (RECOMMENDED)
.HomeworkPage__grid {
  display: grid;
  grid-template-columns: 280px 1fr 400px; // categories | list | preview
  gap: 24px;

  @media (max-width: 1400px) {
    grid-template-columns: 280px 1fr; // collapse preview
  }

  @media (max-width: 768px) {
    grid-template-columns: 1fr; // stack vertically
  }
}
```

### Pattern 2: Visual Selection Feedback
**What:** Consistent hover, active, and selected states using SCSS + BEM
**When to use:** All interactive list items, buttons, cards
**Example:**
```scss
// Source: BEM methodology with SCSS nesting
.HomeworkTaskRow {
  cursor: pointer;
  padding: 16px;
  border-radius: 8px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: $white;
  border: 1px solid $border-default-color;

  // Hover state - subtle elevation and color shift
  &:hover {
    background: $grayscale10;
    border-color: $grayscale30;
    transform: translateY(-2px);
    box-shadow: $card-hover-shadow;
  }

  // Active state - pressed effect
  &:active {
    transform: translateY(0);
    box-shadow: $card-shadow;
  }

  // Selected state - distinct color with brand accent
  &--selected {
    background: lighten($color-primary, 45%);
    border-color: $color-primary;
    border-width: 2px;

    &:hover {
      background: lighten($color-primary, 40%);
    }
  }

  // Focus state for keyboard navigation (WCAG 2.2)
  &:focus-visible {
    outline: 2px solid $color-primary;
    outline-offset: 2px;
  }
}
```

### Pattern 3: Empty State Components
**What:** Informative, actionable empty states with guidance
**When to use:** No homework items, no search results, first-time use
**Example:**
```typescript
// Source: Empty state best practices with context + guidance + visual
interface EmptyStateProps {
  type: 'no-homework' | 'no-results' | 'first-use';
  onAction?: () => void;
}

const HomeworkEmptyState: React.FC<EmptyStateProps> = ({ type, onAction }) => {
  const config = {
    'no-homework': {
      title: 'No homework tasks yet',
      description: 'Create your first homework task to get started',
      action: 'Create Homework',
      icon: <HomeworkIcon />
    },
    'no-results': {
      title: 'No matching homework found',
      description: 'Try adjusting your search or filters',
      action: 'Clear Search',
      icon: <SearchIcon />
    },
    'first-use': {
      title: 'Welcome to Homework Management',
      description: 'Organize therapeutic exercises by topics and assign them to clients',
      action: 'Create First Topic',
      icon: <IntroIcon />
    }
  };

  return (
    <div className="EmptyState">
      {config[type].icon}
      <BaseText type="title">{config[type].title}</BaseText>
      <BaseText type="caption">{config[type].description}</BaseText>
      {onAction && (
        <Button type="primary" onClick={onAction}>
          {config[type].action}
        </Button>
      )}
    </div>
  );
};
```

### Pattern 4: Debounced Search
**What:** Delay search execution until user stops typing
**When to use:** Search inputs that trigger API calls or expensive filters
**Example:**
```typescript
// Current implementation (1000ms delay)
const debounceSearch = useCallback(
  debounce((keyword: string) => {
    getFirstPageListHomework(keyword);
  }, 1000),
  [getFirstPageListHomework],
);

// RECOMMENDED: Reduce to 300-500ms for better UX
const debounceSearch = useCallback(
  debounce((keyword: string) => {
    getFirstPageListHomework(keyword);
  }, 400), // Faster response while still preventing excessive calls
  [getFirstPageListHomework],
);
```

### Anti-Patterns to Avoid

- **Animating width/height in hover states:** Causes expensive layout recalculations. Use transform/opacity instead.
- **Inconsistent state styling:** Different hover effects across similar components confuses users.
- **Missing focus states:** WCAG 2.2 requires keyboard navigation support. Always style :focus-visible.
- **Drag-only interactions:** Must provide alternative input methods (buttons, keyboard) per WCAG 2.5.7.
- **Long debounce delays:** 1000ms feels sluggish. Modern standard is 300-500ms.
- **Unstyled empty states:** Generic "No data" messages miss opportunity to guide users.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Drag and drop | Custom mouse event handlers | react-beautiful-dnd (current) or dnd-kit (future) | Complex event sequencing, touch support, accessibility, collision detection already solved |
| Infinite scrolling | Custom scroll event listeners | react-infinite-scroll-component (existing) | Performance optimization, loading states, edge cases handled |
| Search debouncing | setTimeout/clearTimeout manually | lodash/debounce (existing) | Handles cleanup, cancellation, edge cases correctly |
| Collapse/accordion | Custom toggle logic | Ant Design Collapse (existing) | Animation, keyboard navigation, ARIA attributes built-in |
| Input components | Styled native inputs | Ant Design Input (existing) | Validation, error states, sizing consistency |
| Modal dialogs | Custom overlay + portal | Ant Design Modal (existing) | Focus trap, ESC handling, scroll lock, z-index management |

**Key insight:** React ecosystem has mature solutions for common UI patterns. Custom implementations introduce bugs, accessibility gaps, and maintenance burden. Use proven libraries that align with existing stack (Ant Design 5).

## Common Pitfalls

### Pitfall 1: react-beautiful-dnd Deprecation
**What goes wrong:** Library no longer maintained; security vulnerabilities accumulate
**Why it happens:** Atlassian deprecated in 2022, created pragmatic-drag-and-drop as replacement
**How to avoid:**
- For Phase 02: Keep existing react-beautiful-dnd, document technical debt
- Future phase: Plan migration to dnd-kit (most popular community choice)
- Always provide keyboard/button alternatives per WCAG 2.5.7
**Warning signs:** npm audit warnings, TypeScript type issues with newer React versions

### Pitfall 2: Missing WCAG 2.2 Dragging Alternatives
**What goes wrong:** Users with motor disabilities, speech recognition, or touch-only devices cannot reorder items
**Why it happens:** Developers assume drag-and-drop is sufficient
**How to avoid:**
- Add up/down arrow buttons next to each item
- Provide "Move to position" dropdown
- Support keyboard navigation (ArrowUp/ArrowDown to reorder)
- Test with keyboard only (no mouse)
**Warning signs:** Cannot tab to items, no visible focus indicator, no alternative interaction method

### Pitfall 3: Insufficient Visual Feedback Duration
**What goes wrong:** Hover effects too fast (under 200ms) or too slow (over 500ms)
**Why it happens:** Arbitrary timing choices without UX testing
**How to avoid:**
- Use 0.2s-0.4s for most transitions
- GPU-accelerate with transform/opacity
- Test on slower devices
- Use cubic-bezier easing for natural feel
**Warning signs:** Janky animations, delayed visual response, users miss feedback

### Pitfall 4: Inconsistent Empty States
**What goes wrong:** Some screens show generic "No data", others show helpful guidance
**Why it happens:** Implemented ad-hoc without design system
**How to avoid:**
- Create reusable EmptyState component with types
- Include: title (what's missing) + description (why) + action (how to fix)
- Use consistent illustration style
- Test all empty scenarios
**Warning signs:** User confusion about next steps, support tickets asking "what do I do?"

### Pitfall 5: Mobile Responsiveness Breakage
**What goes wrong:** Three-panel layout doesn't collapse properly on tablets/mobile
**Why it happens:** Desktop-first design, untested breakpoints
**How to avoid:**
- Mobile-first CSS approach
- Test at 360px (mobile), 768px (tablet), 1366px (desktop)
- Use CSS Grid with responsive columns
- Stack panels vertically on small screens
**Warning signs:** Horizontal scrolling on mobile, overlapping panels, hidden content

### Pitfall 6: Search Performance on Large Lists
**What goes wrong:** Debounce too short causes excessive API calls; too long feels sluggish
**Why it happens:** Not tuning debounce delay to actual API response time
**How to avoid:**
- Measure API response time (p50, p95)
- Set debounce to 300-500ms for remote search
- Use client-side filtering for <1000 items
- Show loading indicator if results delayed
**Warning signs:** High API call rate, users complaining about slow search

## Code Examples

Verified patterns from official sources and current implementation:

### Enhanced Hover States with SCSS
```scss
// Source: Current web/src/pages/homework/components/homework-task-row/HomeworkTaskRow.scss
// Enhanced with transition and transform
.HomeworkTaskRow {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  border-bottom: 1px solid $border-default-color;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: $grayscale10;
    transform: translateX(4px);

    .HomeworkTaskRow__icons {
      opacity: 1;
    }
  }

  &:active {
    transform: translateX(2px);
  }

  &--selected {
    background: lighten($color-primary, 45%);
    border-left: 3px solid $color-primary;
  }

  &__icons {
    display: flex;
    gap: 8px;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  // Homework type color indicators
  &.Activity {
    border-left-color: $activity-color;
  }

  &.Questionnaire {
    border-left-color: $question-color;
  }

  &.WrittenTask {
    border-left-color: $written-color;
  }

  &.Video {
    border-left-color: $video-color;
  }
}
```

### Responsive Three-Panel Grid
```scss
// Source: Current web/src/pages/homework/Homework.scss
// Enhanced to three panels
.HomeworkPage__grid {
  display: grid;
  gap: 32px;
  flex: 1;
  min-height: 0;

  // Desktop: three panels (categories | list | preview)
  grid-template-columns: 280px minmax(400px, 1fr) 380px;

  // Large tablet: two panels (categories | list)
  @media (max-width: 1400px) {
    grid-template-columns: 280px 1fr;
    gap: 24px;

    .HomeworkPage__preview {
      display: none; // Hide preview panel
    }
  }

  // Tablet: two panels with narrower categories
  @media (max-width: 1024px) {
    grid-template-columns: 240px 1fr;
    gap: 20px;
  }

  // Mobile: single panel with slide transitions
  @media (max-width: 768px) {
    grid-template-columns: 1fr;
    gap: 0;
    position: relative;
    height: 100%;
  }
}
```

### Accessible Drag Alternative
```typescript
// Source: WCAG 2.2 SC 2.5.7 compliance pattern
interface HomeworkItemProps {
  homework: THomework;
  onMoveUp: () => void;
  onMoveDown: () => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
}

const HomeworkItemWithControls: React.FC<HomeworkItemProps> = ({
  homework,
  onMoveUp,
  onMoveDown,
  canMoveUp,
  canMoveDown
}) => {
  return (
    <div
      className="HomeworkItem"
      draggable
      tabIndex={0}
      role="listitem"
      aria-label={`${homework.title}, use arrow keys or buttons to reorder`}
    >
      <div className="HomeworkItem__content">
        {homework.title}
      </div>
      <div className="HomeworkItem__controls">
        <Button
          icon={<UpOutlined />}
          size="small"
          onClick={onMoveUp}
          disabled={!canMoveUp}
          aria-label="Move up"
        />
        <Button
          icon={<DownOutlined />}
          size="small"
          onClick={onMoveDown}
          disabled={!canMoveDown}
          aria-label="Move down"
        />
      </div>
    </div>
  );
};
```

### Empty State with Action
```typescript
// Source: Empty state best practices - context + guidance + action
import { Empty, Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

const EmptyHomeworkList: React.FC<{ onCreateFirst: () => void }> = ({ onCreateFirst }) => {
  return (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <div className="EmptyHomework">
          <BaseText type="title" className="EmptyHomework__title">
            No homework tasks yet
          </BaseText>
          <BaseText type="caption" className="EmptyHomework__description">
            Create homework tasks to assign therapeutic exercises to your clients
          </BaseText>
        </div>
      }
    >
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={onCreateFirst}
      >
        Create First Homework
      </Button>
    </Empty>
  );
};
```

### Optimized Debounced Search
```typescript
// Source: Current implementation with recommended timing adjustment
import debounce from 'lodash/debounce';
import { useCallback, useState } from 'react';

const useHomeworkSearch = (onSearch: (keyword: string) => Promise<void>) => {
  const [searchKey, setSearchKey] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  const debouncedSearch = useCallback(
    debounce(async (keyword: string) => {
      setIsSearching(true);
      try {
        await onSearch(keyword);
      } finally {
        setIsSearching(false);
      }
    }, 400), // Optimal balance: responsive but not excessive
    [onSearch]
  );

  const handleSearch = (keyword: string) => {
    setSearchKey(keyword);
    debouncedSearch(keyword);
  };

  return { searchKey, isSearching, handleSearch };
};
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| react-beautiful-dnd | dnd-kit / pragmatic-drag-and-drop | 2022-2023 | Better accessibility, modern API, active maintenance |
| Fixed debounce (1000ms) | Adaptive debounce (300-500ms) | 2024-2025 | Faster perceived performance |
| CSS-in-JS | SCSS + CSS Variables | 2023-2024 | Better performance, easier theming |
| Ant Design 4 | Ant Design 5 | 2023 | New design tokens, better TypeScript, improved accessibility |
| Manual focus management | :focus-visible | 2021 (browser support) | Cleaner UI without mouse focus rings |
| WCAG 2.1 AA | WCAG 2.2 AA | 2023 (published Oct 2023) | New requirements for dragging alternatives (SC 2.5.7) |

**Deprecated/outdated:**
- **react-beautiful-dnd:** Still functional but unmaintained. No security updates. Plan migration to dnd-kit.
- **!important in CSS:** Modern specificity management with CSS layers and custom properties preferred.
- **px-only units:** Use rem for typography, px for borders/shadows, % for responsive layouts.
- **Uncontrolled components:** Controlled inputs with proper state management preferred for form validation.

## Open Questions

Things that couldn't be fully resolved:

1. **Should Phase 02 include drag-and-drop migration?**
   - What we know: react-beautiful-dnd works but is deprecated
   - What's unclear: Migration effort vs benefit timeline
   - Recommendation: Keep existing library, document technical debt, plan separate migration phase
   - Rationale: UI/UX improvements are independent of underlying DnD library

2. **What is optimal debounce timing for Antsa's API?**
   - What we know: Current 1000ms, research recommends 300-500ms
   - What's unclear: Actual API response time (p50, p95, p99)
   - Recommendation: Measure production API performance first, then tune debounce
   - Action: Add API response time monitoring, A/B test 400ms vs 1000ms

3. **How should preview panel behavior differ on tablets?**
   - What we know: Desktop shows three panels, mobile stacks vertically
   - What's unclear: Tablet (768px-1400px) should collapse preview or show modal?
   - Recommendation: Hide preview panel below 1400px, use modal on click
   - Action: Create responsive breakpoint tests

4. **Should collapsible categories be expanded by default?**
   - What we know: Current implementation collapses categories
   - What's unclear: User preference data, frequency of category switching
   - Recommendation: Keep Activities expanded by default (most common), others collapsed
   - Action: Add analytics to track category expansion/collapse frequency

5. **What keyboard shortcuts should be supported?**
   - What we know: WCAG requires keyboard navigation, but shortcuts are optional
   - What's unclear: Which shortcuts would be most valuable (J/K for list navigation? Cmd+N for new?)
   - Recommendation: Start with arrow keys for list navigation, add shortcuts in future iteration
   - Action: User research on power user workflows

## Sources

### Primary (HIGH confidence)
- Ant Design 5 official documentation - Component APIs, design tokens, accessibility features
- React-beautiful-dnd GitHub repository - Deprecation notice, migration guidance
- WCAG 2.2 W3C Recommendation - Success Criterion 2.5.7 Dragging Movements
- Current codebase - web/src/pages/homework/Homework.tsx, web/src/themes/_variables.scss
- Playwright official documentation - E2E testing patterns for drag-and-drop

### Secondary (MEDIUM confidence)
- [Top 5 Drag-and-Drop Libraries for React in 2026](https://puckeditor.com/blog/top-5-drag-and-drop-libraries-for-react) - dnd-kit comparison
- [WCAG 2.2 Accessibility Checklist 2026](https://theclaymedia.com/wcag-2-2-accessibility-checklist-2026/) - Dragging movements requirements
- [Responsive Design Breakpoints: 2024 Guide](https://tryhoverify.com/blog/responsive-design-breakpoints-2024-guide/) - Standard breakpoints
- [Getting filters right: UX/UI design patterns](https://blog.logrocket.com/ux-design/filtering-ux-ui-design-patterns-best-practices/) - Search/filter patterns
- [Empty state UX examples and design rules](https://www.eleken.co/blog-posts/empty-state-ux) - Empty state best practices

### Tertiary (LOW confidence - flagged for validation)
- Community blog posts on React design patterns - General guidance, not Antsa-specific
- Stack Overflow discussions on hover timing - Anecdotal preferences, not research-backed
- Medium articles on BEM methodology - Good principles but need verification against current project

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in use, verified in package.json
- Architecture: HIGH - Patterns derived from existing codebase and official Ant Design docs
- Pitfalls: MEDIUM - Based on research and common issues, but not Antsa-specific data
- Accessibility: HIGH - WCAG 2.2 is official W3C standard, requirements clear
- Drag-and-drop: MEDIUM - Research confirms deprecation, but migration timing uncertain

**Research date:** 2026-01-29
**Valid until:** 2026-03-29 (60 days - web UI patterns stable, but framework versions evolve)

**Technologies verified:**
- React 18.2.0 - Confirmed in web/package.json
- Ant Design 5.3.2 - Confirmed in web/package.json
- react-beautiful-dnd 13.1.1 - Confirmed in web/package.json
- SCSS with BEM - Confirmed in web/src/themes/ and component stylesheets
- Playwright configured - Confirmed in web/playwright.config.ts

**Breakpoint testing required:**
- 360px (mobile small)
- 768px (tablet portrait)
- 1024px (tablet landscape)
- 1400px (laptop)
- 1920px (desktop)
