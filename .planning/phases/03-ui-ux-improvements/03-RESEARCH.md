# Phase 03: Comprehensive Web Portal UI/UX Audit and Improvements - Research

**Researched:** 2026-01-29
**Domain:** UI/UX audit methodology, React enterprise portal evaluation, healthcare practitioner workflows
**Confidence:** HIGH

## Summary

This phase focuses on conducting a comprehensive UI/UX audit of the entire practitioner web portal (React 18.2 + Redux + Ant Design 5.3.2 + TypeScript) to identify usability issues, inconsistencies, and improvement opportunities. The user reports "the ux isn't great" - indicating systemic issues requiring structured discovery rather than isolated fixes.

The research reveals that comprehensive UI/UX audits combine multiple methodologies: Nielsen's 10 usability heuristics for expert evaluation, automated accessibility testing with Google Lighthouse, user journey mapping for pain point discovery, design system consistency audits, and healthcare-specific workflow patterns. The web portal spans 22 major feature areas (clients, practitioners, homework, psychoeducation, files, templates, sessions, messages, reports, profile, etc.) requiring systematic feature inventory and prioritized improvements.

**Current State:**
- React 18.2, Ant Design 5.3.2, Redux Toolkit, TypeScript 4.4.2
- ANTSA brand colors defined (_colors.scss): primary #48abe2, success #35d6af, warning #faad14, error #ff7777
- Role-based navigation (clinic owner, solo practitioner, practitioner - different sidebar menus)
- BEM methodology for SCSS styling with established design tokens
- Phase 02 recently completed homework UI/UX improvements (three-panel layout pattern)
- No existing UX audit documentation or component inventory

**Primary recommendation:** Execute structured audit following Nielsen heuristics + automated tooling + user workflow analysis, documenting findings in prioritized backlog using impact-effort matrix, with special attention to healthcare practitioner efficiency patterns.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.2.0 | UI framework | Already in use, component-based architecture |
| Ant Design | 5.3.2 | Enterprise UI components | Already in use, healthcare/admin portal standard |
| TypeScript | 4.4.2 | Type safety | Already in use, interface definitions exist |
| Redux Toolkit | 1.9.3 | State management | Already in use, centralized state |
| SCSS + BEM | 1.53.0 | Styling methodology | Already in use, design tokens defined |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Google Lighthouse | Latest | Automated audits | Performance, accessibility, SEO scoring (30-40% a11y coverage) |
| React DevTools | Latest | Component inspection | Performance profiling, state debugging |
| axe DevTools | Latest (free) | Accessibility testing | More comprehensive than Lighthouse (catches 57% of a11y issues) |
| Chrome DevTools | Built-in | Network/rendering analysis | Performance bottlenecks, layout shifts |
| Playwright | 1.57.0 | E2E testing framework | Already configured, use for user flow testing |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual heuristic eval | User testing only | Heuristics find 80% of issues faster/cheaper than users |
| Google Lighthouse only | Paid tools (Wave, Axe Pro) | Free vs comprehensive coverage (free tools catch 30-57%) |
| Single evaluator | 3-5 evaluators | Single evaluator finds ~35% of issues, 5 find ~75% |
| Comprehensive audit | Ad-hoc fixes | Systemic understanding vs quick wins |

**Installation:**
```bash
# No new production dependencies needed
cd web

# Install audit tooling (dev dependencies)
npm install --save-dev axe-core @axe-core/playwright

# Use existing Playwright for flow testing
# Use browser DevTools for Lighthouse, React DevTools
```

## Architecture Patterns

### Recommended Project Structure
```
web/src/
├── pages/                      # 22+ feature areas to audit
│   ├── home/                  # Dashboard (recently updated)
│   ├── clients/               # Client management + details tabs
│   ├── practitioners/         # Practitioner management
│   ├── homework/              # Phase 02 improvements (baseline)
│   ├── messages/              # Chat/messaging
│   ├── files/                 # File management
│   ├── templates/             # Document templates
│   ├── sessions/              # Sessions (live transcribe + calendar)
│   ├── psycho-education/      # Psychoeducation content
│   ├── report/                # Analytics/reporting
│   ├── profile/               # User profile + settings
│   └── [others]/              # Auth, payment, etc.
├── components/                # Shared UI components
├── layouts/                   # AuthLayout, NonAuthLayout, Header, Sidebar
├── themes/                    # _colors.scss, _variables.scss (design tokens)
└── stores/                    # Redux slices by feature
```

### Pattern 1: Nielsen Heuristic Evaluation Process
**What:** Systematic expert review using 10 usability heuristics
**When to use:** First stage of audit - identifies 75% of major issues with 3-5 evaluators
**Example:**
```typescript
// Heuristic evaluation template structure
interface HeuristicFinding {
  heuristic: 'visibility' | 'match_real_world' | 'user_control' |
             'consistency' | 'error_prevention' | 'recognition' |
             'flexibility' | 'aesthetic' | 'error_recovery' | 'help';
  page: string;                    // e.g., "Clients > Client Details > Homework Tab"
  description: string;             // What's wrong
  severity: 1 | 2 | 3 | 4;        // 1=cosmetic, 4=usability catastrophe
  screenshot?: string;             // Visual evidence
  recommendation: string;          // How to fix
  estimatedEffort: 'low' | 'medium' | 'high';
  estimatedImpact: 'low' | 'medium' | 'high';
}

// Severity rating guide (Nielsen standard)
// 1 = Cosmetic problem only (fix if time permits)
// 2 = Minor usability problem (low priority fix)
// 3 = Major usability problem (important to fix, high priority)
// 4 = Usability catastrophe (imperative to fix before release)
```

### Pattern 2: Feature Inventory Matrix
**What:** Systematic catalog of all features, their purpose, and current state
**When to use:** Discovery phase - understand what exists before evaluating quality
**Example:**
```typescript
interface FeatureInventoryItem {
  area: string;                    // e.g., "Client Management"
  feature: string;                 // e.g., "Client Details Tabs"
  subfeatures: string[];           // e.g., ["General Info", "Homework", "Insight", "Sessions"]
  purpose: string;                 // Why it exists, user goals
  userRole: string[];              // Who uses it (practitioner, owner, etc.)
  currentState: 'working' | 'buggy' | 'confusing' | 'unknown';
  lastUpdated?: string;            // If known (e.g., Phase 02)
  routes: string[];                // URL paths
  relatedComponents: string[];     // Key components used
}

// Example inventory entry
const clientDetailsInventory: FeatureInventoryItem = {
  area: "Client Management",
  feature: "Client Details Page",
  subfeatures: [
    "General Information Tab",
    "Homework Tab",
    "Insight Tab (mood tracking, questionnaires)",
    "Medical Profile Tab",
    "Sessions Tab (transcripts)",
    "Exports Tab",
    "AI Tab"
  ],
  purpose: "View and manage all client information, assign homework, track progress",
  userRole: ["practitioner", "solo_practitioner"],
  currentState: "working",
  lastUpdated: "Phase 02 (homework improvements)",
  routes: ["/clients/:id"],
  relatedComponents: ["ClientDetailsPage", "HomeworkTab", "InsightTab", "etc."]
};
```

### Pattern 3: User Journey Pain Point Mapping
**What:** Map practitioner workflows to identify friction points
**When to use:** After feature inventory - understand real-world usage patterns
**Example:**
```typescript
interface UserJourney {
  persona: string;                 // "Solo Practitioner", "Clinic Owner", etc.
  scenario: string;                // "Assign homework after session"
  steps: JourneyStep[];
  painPoints: PainPoint[];
  successMetrics: string[];        // How to measure improvement
}

interface JourneyStep {
  step: number;
  action: string;                  // What user does
  page: string;                    // Where they are
  expectedOutcome: string;         // What should happen
  actualExperience: string;        // What actually happens
  emotionalState?: 'confused' | 'frustrated' | 'neutral' | 'satisfied';
}

interface PainPoint {
  step: number;
  issue: string;                   // Specific problem
  frequency: 'always' | 'often' | 'sometimes' | 'rare';
  impact: 'blocks_task' | 'slows_task' | 'annoys_user' | 'minor';
  evidence?: string;               // User feedback, analytics, observation
}
```

### Pattern 4: Design System Consistency Audit
**What:** Check all UI elements against ANTSA design tokens and patterns
**When to use:** Parallel to heuristic evaluation - identify visual inconsistencies
**Example:**
```typescript
interface DesignConsistencyIssue {
  category: 'color' | 'typography' | 'spacing' | 'component_variant' | 'interaction';
  location: string;                // Component or page
  issue: string;                   // What's inconsistent
  expected: string;                // Should use X (from design tokens)
  actual: string;                  // Currently uses Y
  impact: 'visual_inconsistency' | 'accessibility_issue' | 'brand_deviation';
}

// Example: Check all color usage against _colors.scss
const colorAudit = {
  category: 'color',
  location: 'HomePage > DashboardCard',
  issue: 'Hardcoded color instead of semantic token',
  expected: '$color-primary (#48abe2)',
  actual: '#1890ff (Ant Design default blue)',
  impact: 'brand_deviation'
};
```

### Pattern 5: Impact-Effort Prioritization Matrix
**What:** Prioritize findings using 2x2 matrix (effort vs impact)
**When to use:** After collecting findings - create actionable backlog
**Example:**
```typescript
interface PrioritizedFinding {
  finding: HeuristicFinding | DesignConsistencyIssue | PainPoint;
  effort: 'low' | 'medium' | 'high';      // Dev time to fix
  impact: 'low' | 'medium' | 'high';      // User/business value
  priority: 'quick_win' | 'major_project' | 'fill_in' | 'thankless_task';
}

// Priority mapping (Impact-Effort Matrix)
// High Impact + Low Effort = Quick Win (DO FIRST)
// High Impact + High Effort = Major Project (PLAN CAREFULLY)
// Low Impact + Low Effort = Fill In (DO IF TIME)
// Low Impact + High Effort = Thankless Task (AVOID/LAST)

const calculatePriority = (impact: string, effort: string): string => {
  if (impact === 'high' && effort === 'low') return 'quick_win';
  if (impact === 'high' && effort === 'high') return 'major_project';
  if (impact === 'low' && effort === 'low') return 'fill_in';
  return 'thankless_task';
};
```

### Pattern 6: Healthcare Practitioner Workflow Patterns
**What:** Healthcare-specific UX patterns for efficiency
**When to use:** Evaluating any practitioner-facing workflows
**Key Patterns:**
- **Patient lookup optimization:** Fast search, recent clients, visual identification (photo)
- **Task batching:** Bulk actions for common workflows (assign homework to multiple clients)
- **Context preservation:** Don't lose data on navigation, auto-save drafts
- **Status visibility:** Clear indicators for client status, pending tasks, unread messages
- **Quick access:** Frequently used actions accessible in 1-2 clicks
- **Minimal data entry:** Pre-fill known information, templates, copy-from-previous

### Anti-Patterns to Avoid

- **Single evaluator audit:** Finds only ~35% of issues vs 75% with 3-5 evaluators
- **No severity ratings:** All issues treated equally leads to poor prioritization
- **Audit without user context:** Missing real-world workflows and pain points
- **No baseline metrics:** Can't measure improvement without before/after data
- **Comprehensive report, no action:** Audit findings must convert to prioritized backlog
- **Ignoring accessibility:** 15-20% of users have disabilities, impacts everyone
- **Aesthetic-only focus:** Pretty but unusable is worse than functional but plain
- **No follow-up validation:** Fixes should be tested to confirm improvement

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Heuristic evaluation forms | Custom spreadsheets | Figma templates, structured docs | Standardized format, easier consolidation, includes severity scales |
| Accessibility testing | Manual WCAG checks | Lighthouse + axe DevTools | Automated testing catches 30-57% of issues instantly |
| User flow recording | Manual notes | Playwright traces, session recordings | Captures exact reproduction steps, screenshots, network logs |
| Impact-effort matrices | Static diagrams | Interactive tools (Miro, FigJam) | Easy to reorganize priorities, collaborative, visual |
| Design token audits | Manual file searching | CSS/SCSS linters, Stylelint | Automated detection of hardcoded values vs tokens |
| Component inventory | Manual documentation | Storybook + Chromatic | Living documentation, visual regression testing |

**Key insight:** UI/UX audits generate massive amounts of data (hundreds of findings). Use structured templates and automation tools from the start to avoid drowning in unorganized notes. Spend time analyzing patterns, not organizing spreadsheets.

## Common Pitfalls

### Pitfall 1: Boiling the Ocean
**What goes wrong:** Try to audit everything at once, get overwhelmed, audit never completes
**Why it happens:** 22+ feature areas in web portal, each with multiple workflows
**How to avoid:**
- Phase the audit: P1 = high-traffic areas (home, clients, homework), P2 = medium traffic, P3 = admin/settings
- Set time boundaries: 2-3 weeks max for discovery, 1 week for prioritization
- Focus on systemic issues vs one-off bugs (save bugs for issue tracker)
- Use 80/20 rule: 80% of user time spent in 20% of features
**Warning signs:** Audit extending past 4 weeks, hundreds of minor findings, no clear priorities

### Pitfall 2: Expert Evaluation Without User Evidence
**What goes wrong:** Experts find issues users don't care about, miss issues users struggle with
**Why it happens:** Relying solely on heuristic evaluation without validating assumptions
**How to avoid:**
- Combine heuristics with quantitative data (analytics: bounce rates, time-on-task)
- Review support tickets for common user complaints
- Include user feedback quotes in findings
- Prioritize issues that block real workflows
**Warning signs:** All findings from one person's opinion, no usage data, theoretical scenarios

### Pitfall 3: Accessibility Audit Theater
**What goes wrong:** Run Lighthouse, get 95+ score, claim "accessible", but real users can't use it
**Why it happens:** Automated tools only catch 30-40% of accessibility issues
**How to avoid:**
- Manual keyboard navigation testing (Tab, Enter, Escape, Arrow keys)
- Screen reader testing (NVDA free, macOS VoiceOver built-in)
- Check for cognitive accessibility (clear language, error prevention)
- Test with real assistive technology users if possible
**Warning signs:** Perfect Lighthouse score but no manual testing, no keyboard testing

### Pitfall 4: No Severity Distinction
**What goes wrong:** Report lists 200 findings equally, team paralyzed by volume
**Why it happens:** No systematic severity rating during audit collection
**How to avoid:**
- Use Nielsen 4-point severity scale (1=cosmetic, 4=catastrophe)
- Rate during audit, not after (context fresh)
- Include severity in finding template as required field
- Filter reports: exec summary = severity 3-4 only, detailed = all
**Warning signs:** Flat list of findings, no priority indicators, "fix everything" mentality

### Pitfall 5: Design Consistency Audit Without Baseline
**What goes wrong:** Identify inconsistencies but no agreed-upon "correct" version
**Why it happens:** Design tokens exist but not documented or inconsistently applied
**How to avoid:**
- Start by documenting current design tokens (_colors.scss, _variables.scss)
- Identify canonical examples (e.g., Phase 02 homework as reference)
- Create visual style guide from existing tokens before audit
- Consistency issues must reference specific token/pattern
**Warning signs:** "This should be more consistent" without defining with what

### Pitfall 6: Healthcare Workflow Misunderstanding
**What goes wrong:** Optimize for wrong workflows, break practitioner efficiency
**Why it happens:** Auditors unfamiliar with mental health practice patterns
**How to avoid:**
- Review all 22+ feature areas to understand relationships
- Map common practitioner workflows (session → homework → notes → client update)
- Understand role differences (solo practitioner vs clinic owner vs practitioner)
- Preserve efficient patterns even if unconventional
**Warning signs:** Recommendations that add clicks to common tasks, breaking bulk operations

### Pitfall 7: Audit Report Graveyard
**What goes wrong:** Comprehensive audit completed, report filed, nothing happens
**Why it happens:** No clear ownership, no prioritization, no roadmap integration
**How to avoid:**
- Convert findings to actionable tasks during audit (not after)
- Use impact-effort matrix to identify "quick wins" (high impact, low effort)
- Create phases: immediate fixes (1-2 weeks), short-term (1-2 months), long-term (3-6 months)
- Assign owners to phases, not entire audit
**Warning signs:** Audit doc sits in Google Drive, no GitHub issues created, "we'll get to it later"

## Code Examples

Verified patterns from official sources and current implementation:

### Nielsen Heuristic Evaluation Template
```markdown
# UI/UX Audit - Heuristic Evaluation

## Audit Metadata
- **Evaluator:** [Name]
- **Date:** [Date]
- **Pages Audited:** [List]
- **Methodology:** Nielsen's 10 Usability Heuristics

## Heuristic 1: Visibility of System Status
*Keep users informed about what's going on through appropriate feedback within reasonable time.*

### Finding 1.1
- **Page:** Homework > Assign Homework
- **Issue:** No loading indicator when saving homework assignment
- **Severity:** 3 (Major - user doesn't know if action succeeded)
- **Screenshot:** [link]
- **Recommendation:** Add loading spinner + success toast notification
- **Impact:** High (causes users to click multiple times, duplicate assignments)
- **Effort:** Low (Ant Design Spin + message components exist)

### Finding 1.2
- **Page:** [Next finding...]

## Heuristic 2: Match Between System and Real World
*Speak the users' language with words, phrases, and concepts familiar to the user.*

[Continue for all 10 heuristics...]

## Summary Statistics
- Total findings: X
- Severity 4 (Catastrophic): X
- Severity 3 (Major): X
- Severity 2 (Minor): X
- Severity 1 (Cosmetic): X
- Quick wins identified: X (high impact + low effort)
```

### Automated Accessibility Testing Script
```typescript
// web/tests/accessibility-audit.spec.ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Test all major pages for accessibility violations
const pagesToTest = [
  { path: '/', name: 'Home/Dashboard' },
  { path: '/clients', name: 'Clients List' },
  { path: '/homework', name: 'Homework Management' },
  { path: '/practitioners', name: 'Practitioners (Owner)' },
  { path: '/profile', name: 'Profile Settings' },
  { path: '/sessions', name: 'Sessions' },
  { path: '/files', name: 'Files' },
  { path: '/templates', name: 'Templates' },
  // Add all 22+ areas
];

for (const page of pagesToTest) {
  test(`Accessibility audit: ${page.name}`, async ({ page: playwrightPage }) => {
    await playwrightPage.goto(page.path);

    // Wait for page to be interactive
    await playwrightPage.waitForLoadState('networkidle');

    // Run axe accessibility scan
    const accessibilityScanResults = await new AxeBuilder({ page: playwrightPage })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    // Output results to JSON for reporting
    console.log(JSON.stringify(accessibilityScanResults.violations, null, 2));

    // Fail test if critical violations found
    expect(accessibilityScanResults.violations).toEqual([]);
  });
}

// Run with: npm run test:e2e -- accessibility-audit.spec.ts
```

### Feature Inventory Data Structure
```typescript
// .planning/phases/03-ui-ux-improvements/feature-inventory.ts
export interface FeatureArea {
  id: string;
  name: string;
  description: string;
  routes: string[];
  userRoles: string[];
  components: string[];
  status: 'active' | 'beta' | 'deprecated';
  lastAudit?: string;
  priority: 'high_traffic' | 'medium_traffic' | 'low_traffic';
}

export const FEATURE_INVENTORY: FeatureArea[] = [
  {
    id: 'home-dashboard',
    name: 'Home Dashboard',
    description: 'Landing page with practitioner stats, messages, quote of the day, training materials',
    routes: ['/'],
    userRoles: ['practitioner', 'solo_practitioner', 'owner', 'clinic_owner'],
    components: ['Home.tsx', 'DashboardCard', 'WelcomeBanner', 'MessageOfTheDay'],
    status: 'active',
    lastAudit: '2026-01-29',
    priority: 'high_traffic'
  },
  {
    id: 'clients-management',
    name: 'Client Management',
    description: 'List, search, filter, and manage clients',
    routes: ['/clients'],
    userRoles: ['practitioner', 'solo_practitioner'],
    components: ['ClientsPage', 'ClientList', 'ClientCard'],
    status: 'active',
    priority: 'high_traffic'
  },
  {
    id: 'client-details',
    name: 'Client Details',
    description: 'Comprehensive client information with tabs: general, homework, insight, medical, sessions, exports, AI',
    routes: ['/clients/:id'],
    userRoles: ['practitioner', 'solo_practitioner'],
    components: ['ClientDetailsPage', 'HomeworkTab', 'InsightTab', 'MedicalProfile', 'LiveTranscribeTab', 'ExportsTab', 'AITab'],
    status: 'active',
    priority: 'high_traffic'
  },
  {
    id: 'homework-management',
    name: 'Homework Management',
    description: 'Create, organize, and assign therapeutic homework tasks',
    routes: ['/homework', '/homework/bulk-assign'],
    userRoles: ['practitioner', 'solo_practitioner'],
    components: ['Homework', 'HomeworkList', 'HomeworkTaskRow', 'BulkAssignHomework'],
    status: 'active',
    lastAudit: '2026-01-29 (Phase 02)',
    priority: 'high_traffic'
  },
  // Continue for all 22+ areas...
  {
    id: 'practitioners-management',
    name: 'Practitioners Management',
    description: 'Clinic owners manage practitioner accounts, assign clients',
    routes: ['/practitioners', '/practitioners/:id'],
    userRoles: ['owner', 'clinic_owner'],
    components: ['PractitionersPage', 'PractitionerDetailsPage', 'AssignClientsModal'],
    status: 'active',
    priority: 'medium_traffic'
  },
  {
    id: 'messages-chat',
    name: 'Messages / Chat',
    description: 'Real-time messaging with clients',
    routes: ['/messages'],
    userRoles: ['practitioner', 'solo_practitioner'],
    components: ['MessagesPages', 'ChatItem'],
    status: 'active',
    priority: 'high_traffic'
  },
  {
    id: 'sessions',
    name: 'Sessions (Live Transcribe + Calendar)',
    description: 'Session management, live transcription, video calls, calendar',
    routes: ['/sessions', '/video-call/:roomId'],
    userRoles: ['practitioner', 'solo_practitioner'],
    components: ['SessionsPage', 'LiveTranscribePage', 'VideoCallRoom'],
    status: 'active',
    priority: 'high_traffic'
  },
  {
    id: 'files-management',
    name: 'Files Management',
    description: 'Shared file storage and organization',
    routes: ['/files', '/files/:folderId'],
    userRoles: ['practitioner', 'solo_practitioner', 'owner', 'clinic_owner'],
    components: ['FilesPages', 'NewFolderModal'],
    status: 'active',
    priority: 'medium_traffic'
  },
  {
    id: 'templates',
    name: 'Document Templates',
    description: 'Session note templates, document generation',
    routes: ['/templates', '/templates/:id'],
    userRoles: ['practitioner', 'solo_practitioner', 'owner', 'clinic_owner'],
    components: ['TemplatesPage', 'TemplateViewPage'],
    status: 'active',
    priority: 'medium_traffic'
  },
  {
    id: 'psychoeducation',
    name: 'Psychoeducation',
    description: 'Educational content and resources',
    routes: ['/psychoeducation'],
    userRoles: ['practitioner', 'solo_practitioner'],
    components: ['PsychoeducationPage', 'PsychoeducationTopicList', 'PsychoeducationItem'],
    status: 'active',
    priority: 'medium_traffic'
  },
  {
    id: 'reports-analytics',
    name: 'Reports & Analytics',
    description: 'Dashboard analytics, client engagement, practitioner engagement',
    routes: ['/report'],
    userRoles: ['practitioner', 'solo_practitioner', 'owner', 'clinic_owner'],
    components: ['ReportPage', 'SummaryComponent', 'ClientEngagementChart', 'PractitionerEngagementChart'],
    status: 'active',
    priority: 'medium_traffic'
  },
  {
    id: 'profile-settings',
    name: 'Profile & Settings',
    description: 'User settings, subscription, payment, notifications, clinic info',
    routes: ['/profile'],
    userRoles: ['practitioner', 'solo_practitioner', 'owner', 'clinic_owner'],
    components: ['ProfilePage', 'GeneralInformation', 'ClinicInformation', 'PaymentMethod', 'Notification', 'Privacy', 'Term'],
    status: 'active',
    priority: 'low_traffic'
  },
  // Add: payment, pricing, auth pages, etc.
];
```

### Impact-Effort Matrix Visualization
```typescript
// Tool: Generate prioritization matrix from findings
interface Finding {
  id: string;
  title: string;
  impact: 'low' | 'medium' | 'high';
  effort: 'low' | 'medium' | 'high';
  severity: 1 | 2 | 3 | 4;
}

const findings: Finding[] = [
  {
    id: 'F001',
    title: 'Missing loading indicators on async actions',
    impact: 'high',      // Users confused, duplicate actions
    effort: 'low',       // Ant Design Spin component exists
    severity: 3
  },
  {
    id: 'F002',
    title: 'Inconsistent button colors (not using design tokens)',
    impact: 'low',       // Visual inconsistency only
    effort: 'low',       // Find/replace + lint rule
    severity: 1
  },
  {
    id: 'F003',
    title: 'Complex navigation to assign homework (5+ clicks)',
    impact: 'high',      // Core workflow, used daily
    effort: 'high',      // Requires redesign + testing
    severity: 3
  },
  // ... more findings
];

// Categorize by quadrant
const quickWins = findings.filter(f => f.impact === 'high' && f.effort === 'low');
const majorProjects = findings.filter(f => f.impact === 'high' && f.effort === 'high');
const fillIns = findings.filter(f => f.impact === 'low' && f.effort === 'low');
const thanklessTasks = findings.filter(f => f.impact === 'low' && f.effort === 'high');

console.log('QUICK WINS (Do First):', quickWins.length);
console.log('MAJOR PROJECTS (Plan Carefully):', majorProjects.length);
console.log('FILL INS (If Time Allows):', fillIns.length);
console.log('THANKLESS TASKS (Deprioritize):', thanklessTasks.length);

// Export to markdown table for planning doc
const generatePriorityTable = (findings: Finding[]) => {
  return findings.map(f =>
    `| ${f.id} | ${f.title} | ${f.impact} | ${f.effort} | ${f.severity} |`
  ).join('\n');
};
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual accessibility checks | Automated tools (Lighthouse, axe) + manual testing | 2020-2023 | Catches 30-57% of issues automatically, faster audits |
| Single expert review | 3-5 independent evaluators | Nielsen research (1990s) | Finds 75% vs 35% of issues |
| Ad-hoc user feedback | Systematic user journey mapping | 2015-2020 | Identifies systemic issues vs anecdotes |
| Post-launch only audits | Continuous UX monitoring | 2020-2025 | Proactive vs reactive improvement |
| Design handoff disconnects | Figma-Storybook integration | 2022-2024 | Design-code consistency, living documentation |
| Impact-effort gut feeling | Data-driven prioritization matrices | 2018-2023 | Objective prioritization, clear ROI |
| WCAG 2.1 AA | WCAG 2.2 AA (Oct 2023) | 2023 | New requirements (focus appearance, dragging alternatives) |

**Deprecated/outdated:**
- **Manual-only accessibility testing:** Automated tools now catch 30-57% instantly (Lighthouse, axe)
- **Single-heuristic frameworks:** Nielsen's 10 remain standard, but augmented with healthcare-specific patterns
- **Audit reports as final deliverable:** Modern practice converts findings to prioritized backlog immediately
- **Desktop-only audits:** Mobile responsiveness now table stakes for all web apps
- **Waterfall audit process:** Modern audits integrate with agile sprints, continuous improvement

## Open Questions

Things that couldn't be fully resolved:

1. **What are the top user complaints?**
   - What we know: User stated "the ux isn't great" (general feedback)
   - What's unclear: Specific pain points, frequency, which features affected
   - Recommendation: Review support tickets, chat logs, user feedback for patterns
   - Action: Include in Phase 03 discovery - analyze existing feedback data

2. **What are actual usage patterns?**
   - What we know: 22+ feature areas exist, roles defined (practitioner, owner, etc.)
   - What's unclear: Which features used most, time-on-task, bounce rates, conversion funnels
   - Recommendation: Set up analytics if not exists, analyze existing data if available
   - Action: Phase 03 should include quantitative analysis (Google Analytics, session replays if available)

3. **Are there existing user personas or journey maps?**
   - What we know: Three main roles (solo practitioner, practitioner, clinic owner)
   - What's unclear: Documented personas, typical workflows, job stories
   - Recommendation: Create if don't exist, validate if do exist
   - Action: Part of Phase 03 discovery - document or validate personas

4. **What is the baseline for "good UX" in this domain?**
   - What we know: Phase 02 homework improvements provide one reference point
   - What's unclear: Company UX standards, competitor benchmarks, user expectations
   - Recommendation: Define success metrics before audit (task completion rate, time-on-task, satisfaction score)
   - Action: Establish baseline metrics during Phase 03 planning

5. **How much technical debt exists?**
   - What we know: React-beautiful-dnd deprecated (Phase 02 research), TypeScript 4.4.2 (current stable is 5.x)
   - What's unclear: Full technical debt inventory, security vulnerabilities, outdated patterns
   - Recommendation: Separate technical debt audit from UX audit (different skills, priorities)
   - Action: Note technical issues during UX audit but track separately

6. **What is the improvement budget/timeline?**
   - What we know: Phase-based approach used (Phase 01, 02 complete)
   - What's unclear: How many phases for Phase 03 findings, resource availability
   - Recommendation: Prioritize with impact-effort matrix, phase in sprints (quick wins first)
   - Action: Create multi-phase roadmap from audit findings (immediate, short-term, long-term)

## Sources

### Primary (HIGH confidence)
- [Nielsen's 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) - Industry standard heuristic evaluation framework
- [How to Conduct a Heuristic Evaluation - NN/G](https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/) - Methodology guide
- [Google Lighthouse Documentation](https://developer.chrome.com/docs/lighthouse/overview/) - Automated audit tool
- [Lighthouse Accessibility Score](https://developer.chrome.com/docs/lighthouse/accessibility/scoring) - Uses axe-core, catches 30-40% of issues
- [Ant Design Design Spec](https://ant.design/docs/spec/overview/) - Enterprise UI guidelines
- Current codebase: web/src/pages/, web/src/themes/_colors.scss, web/package.json
- Phase 02 Research: .planning/phases/02-homework-ui-ux/02-RESEARCH.md (baseline patterns)

### Secondary (MEDIUM confidence)
- [UX Design Audit Checklist - Eleken](https://www.eleken.co/blog-posts/a-checklist-for-ux-design-audit-based-on-jakob-nielsens-10-usability-heuristics) - Practical checklist based on Nielsen
- [UX Audit Checklist: 7 Steps - Maze](https://maze.co/collections/ux-ui-design/ux-audit/) - Comprehensive audit methodology
- [Impact Effort Matrix - Alyssum Digital](https://alyssumdigital.com/blog/how-to-turn-ux-audit-findings-into-action-using-impact-effort-matrix) - Prioritization approach
- [Best UX/UI Design Practices for Healthcare Apps](https://www.capminds.com/blog/best-practices-in-ux-ui-design-for-healthcare-apps/) - Domain-specific patterns
- [Healthcare UI Design 2025: Best Practices + Examples](https://www.eleken.co/blog-posts/user-interface-design-for-healthcare-applications) - Healthcare UX patterns
- [Design System Consistency Audit](https://www.uxpin.com/studio/blog/launching-design-system-checklist/) - Component library audit methodology
- [User Journey Mapping Pain Points](https://contentsquare.com/guides/user-journey/ux-pain-points/) - Discovery techniques

### Tertiary (LOW confidence - flagged for validation)
- Web search results on "UI/UX audit methodology 2026" - General best practices, not Antsa-specific
- Web search results on "practitioner portal UX patterns" - Healthcare patterns, need domain validation
- Community blog posts on React auditing - General guidance, verify against Ant Design specifics

## Metadata

**Confidence breakdown:**
- Audit methodology: HIGH - Nielsen heuristics are industry standard, well-documented
- Healthcare patterns: MEDIUM - General healthcare UX patterns found, but mental health practitioner specifics need validation
- Current codebase understanding: HIGH - Direct inspection of package.json, routes, themes, Phase 02 research
- Tooling recommendations: HIGH - Lighthouse, axe, Playwright already in use or widely adopted
- Prioritization approach: HIGH - Impact-effort matrices are standard practice with clear methodology

**Research date:** 2026-01-29
**Valid until:** 2026-03-29 (60 days - UX audit methodologies stable, but codebase evolves)

**Technologies verified:**
- React 18.2.0 - Confirmed in web/package.json
- Ant Design 5.3.2 - Confirmed in web/package.json
- Redux Toolkit 1.9.3 - Confirmed in web/package.json
- TypeScript 4.4.2 - Confirmed in web/package.json
- Playwright 1.57.0 - Confirmed in web/package.json
- SCSS + BEM - Confirmed in web/src/themes/ and component files
- ANTSA colors - Confirmed in web/src/themes/_colors.scss (primary: #48abe2)

**Audit scope:**
- 22+ feature areas identified across web portal
- 4 user roles: practitioner, solo_practitioner, owner, clinic_owner
- Multiple layouts: AuthLayout, NonAuthLayout, Header, Sidebar
- Role-based navigation patterns
- Recently updated: Phase 02 homework improvements (baseline reference)
