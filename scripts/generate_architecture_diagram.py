#!/usr/bin/env python3
"""
Generate professional architecture diagram for DIA Optimization System.
Follows Google Cloud brand standards with clean, executive-ready design.
Fixed layout with no overlapping elements.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
import matplotlib.lines as mlines

# Google Cloud Brand Color Palette (Official)
GCP_BLUE = '#4285F4'
GCP_RED = '#EA4335'
GCP_YELLOW = '#FBBC04'
GCP_GREEN = '#34A853'
CLOUD_GRAY = '#5F6368'
LIGHT_GRAY = '#E8EAED'
WHITE = '#FFFFFF'
BACKGROUND = '#F8F9FA'

def create_component_box(ax, xy, width, height, title, subtitle_lines, color, alpha=1.0):
    """Create a professional component box with title and bullet points."""
    x, y = xy

    # Main box
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02",
        edgecolor=color,
        facecolor=WHITE,
        linewidth=2.5,
        alpha=alpha,
        zorder=2
    )
    ax.add_patch(box)

    # Title bar
    title_bar = Rectangle(
        (x, y + height - 0.35), width, 0.35,
        facecolor=color,
        edgecolor='none',
        alpha=0.95,
        zorder=3
    )
    ax.add_patch(title_bar)

    # Title text
    ax.text(
        x + width/2, y + height - 0.175,
        title,
        ha='center', va='center',
        color=WHITE,
        fontsize=9,
        fontweight='bold',
        family='sans-serif',
        zorder=4
    )

    # Subtitle content
    y_offset = y + height - 0.55
    for line in subtitle_lines:
        ax.text(
            x + 0.1, y_offset,
            line,
            ha='left', va='top',
            color=CLOUD_GRAY,
            fontsize=7,
            family='sans-serif',
            zorder=4
        )
        y_offset -= 0.15

def create_clean_arrow(ax, start, end, color=CLOUD_GRAY, label='', style='->', lw=2.5):
    """Create a clean arrow with optional label."""
    arrow = FancyArrowPatch(
        start, end,
        arrowstyle=style,
        color=color,
        linewidth=lw,
        linestyle='-',
        mutation_scale=25,
        alpha=0.8,
        zorder=1
    )
    ax.add_patch(arrow)

    if label:
        mid_x, mid_y = (start[0] + end[0])/2, (start[1] + end[1])/2
        ax.text(mid_x, mid_y, label,
                ha='center', va='bottom',
                fontsize=7, color=color, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=WHITE, edgecolor='none', alpha=0.95),
                zorder=5)

def main():
    # Create figure with professional dimensions
    fig = plt.figure(figsize=(20, 14))
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 14)
    ax.axis('off')

    # Set background
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)

    # ===== HEADER =====
    ax.text(10, 13.3, 'Data Insights Agent Optimization System',
            ha='center', fontsize=22, fontweight='bold', color=CLOUD_GRAY,
            family='sans-serif')
    ax.text(10, 12.85, 'Automated AI-Driven NL2SQL Improvement via Hill Climbing',
            ha='center', fontsize=11, color=CLOUD_GRAY, style='italic',
            family='sans-serif')

    # Google Cloud logo text
    ax.text(0.5, 13.3, 'Google Cloud',
            ha='left', fontsize=11, fontweight='bold', color=GCP_BLUE,
            family='sans-serif')

    # ===== LAYER 1: USER INTERFACE (Top) =====
    y_ui = 11.5

    ax.text(1, y_ui + 0.4, 'USER INTERFACE',
            ha='left', fontsize=9, fontweight='bold', color=CLOUD_GRAY,
            family='sans-serif', bbox=dict(boxstyle='round,pad=0.3', facecolor=LIGHT_GRAY, edgecolor='none'))

    create_component_box(ax, (1, y_ui - 0.9), 2.8, 1.2,
                        'CLI: Deploy',
                        ['• dia-harness deploy', '• Agent setup', '• OAuth config'],
                        GCP_GREEN)

    create_component_box(ax, (4.2, y_ui - 0.9), 2.8, 1.2,
                        'CLI: Optimize',
                        ['• dia-harness optimize', '• Auto-accept mode', '• 15 iterations'],
                        GCP_BLUE)

    create_component_box(ax, (7.4, y_ui - 0.9), 2.8, 1.2,
                        'Report Generator',
                        ['• Charts & metrics', '• Markdown reports', '• Artifacts'],
                        GCP_YELLOW)

    # ===== LAYER 2: ORCHESTRATION ENGINE =====
    y_orch = 8.8

    ax.text(1, y_orch + 0.4, 'ORCHESTRATION LAYER',
            ha='left', fontsize=9, fontweight='bold', color=CLOUD_GRAY,
            family='sans-serif', bbox=dict(boxstyle='round,pad=0.3', facecolor=LIGHT_GRAY, edgecolor='none'))

    create_component_box(ax, (1, y_orch - 1.3), 7, 1.6,
                        'Iterative Optimizer (Hill Climbing)',
                        ['Deploy Config → Evaluate (2 repeats × 17 tests) → Analyze Failures',
                         'AI-Generate Improvements → Validate → PATCH Agent → Repeat'],
                        GCP_BLUE)

    # Sub-components (right side - NOT overlapping artifacts box)
    create_component_box(ax, (8.5, y_orch + 0.1), 2.2, 0.85,
                        'Config Deployer',
                        ['PATCH API', 'Validation'],
                        GCP_GREEN, alpha=0.95)

    create_component_box(ax, (11, y_orch + 0.1), 2.2, 0.85,
                        'Evaluator',
                        ['Retry logic', 'Aggregation'],
                        GCP_BLUE, alpha=0.95)

    create_component_box(ax, (13.5, y_orch + 0.1), 2.2, 0.85,
                        'Tracker',
                        ['Trajectory', 'Rollback'],
                        GCP_YELLOW, alpha=0.95)

    # ===== OUTPUT ARTIFACTS (Right side panel - BELOW sub-components) =====
    artifact_box = FancyBboxPatch(
        (8.5, y_orch - 1.3), 7.2, 1.2,
        boxstyle="round,pad=0.05",
        edgecolor=CLOUD_GRAY,
        facecolor='#E6F4EA',
        linewidth=2,
        alpha=0.9,
        zorder=2
    )
    ax.add_patch(artifact_box)

    ax.text(9, y_orch - 0.95, 'OUTPUT ARTIFACTS',
            ha='left', fontsize=8, fontweight='bold', color=CLOUD_GRAY,
            family='sans-serif', zorder=4)

    artifact_text = """• trajectory_history_<run_id>.json
• eval_train_<run_id>.jsonl (×2 repeats)
• OPTIMIZATION_REPORT_<run_id>.md
• charts/*.png (6 visualizations)"""

    ax.text(9, y_orch - 1.2, artifact_text,
            ha='left', va='top',
            fontsize=6.5,
            color=CLOUD_GRAY,
            family='monospace',
            linespacing=1.5,
            zorder=4)

    # ===== LAYER 3: GOOGLE CLOUD PLATFORM =====
    y_gcp = 5.2

    # Large GCP container
    gcp_container = FancyBboxPatch(
        (1, y_gcp - 2.3), 14.7, 2.8,
        boxstyle="round,pad=0.05",
        edgecolor=GCP_BLUE,
        facecolor=WHITE,
        linewidth=3,
        alpha=0.98,
        zorder=2
    )
    ax.add_patch(gcp_container)

    ax.text(1.5, y_gcp + 0.4, 'GOOGLE CLOUD PLATFORM SERVICES',
            ha='left', fontsize=10, fontweight='bold', color=GCP_BLUE,
            family='sans-serif', zorder=4)

    # Vertex AI Gemini Enterprise
    create_component_box(ax, (1.5, y_gcp - 2.0), 3.5, 2.2,
                        'Vertex AI Gemini',
                        ['Data Insights Agent',
                         '• NL2SQL Prompt',
                         '• Schema Description',
                         '• Few-Shot Examples'],
                        GCP_BLUE)

    # AI Services (3 stacked)
    create_component_box(ax, (5.5, y_gcp + 0.05), 2.8, 0.65,
                        'Judgement Model',
                        ['Gemini: SQL Equivalence'],
                        GCP_RED, alpha=0.95)

    create_component_box(ax, (5.5, y_gcp - 0.7), 2.8, 0.65,
                        'Config Analyzer',
                        ['Gemini: Field Analysis'],
                        GCP_YELLOW, alpha=0.95)

    create_component_box(ax, (5.5, y_gcp - 1.45), 2.8, 0.65,
                        'Prompt Improver',
                        ['Gemini: NL Generation'],
                        GCP_GREEN, alpha=0.95)

    # BigQuery
    create_component_box(ax, (8.8, y_gcp - 2.0), 3.2, 2.2,
                        'BigQuery',
                        ['Sales Data',
                         'Market Dimensions',
                         'Calendar Facts',
                         '17 Test Cases'],
                        GCP_BLUE)

    # OAuth
    create_component_box(ax, (12.5, y_gcp - 1.3), 2.7, 1.5,
                        'OAuth 2.0',
                        ['Authorization',
                         'BigQuery Access',
                         'Credentials'],
                        GCP_GREEN, alpha=0.95)

    # ===== LAYER 4: EVALUATION PIPELINE =====
    y_eval = 1.8

    ax.text(1, y_eval + 0.4, 'EVALUATION & FEEDBACK',
            ha='left', fontsize=9, fontweight='bold', color=CLOUD_GRAY,
            family='sans-serif', bbox=dict(boxstyle='round,pad=0.3', facecolor=LIGHT_GRAY, edgecolor='none'))

    # Evaluation components
    eval_boxes = [
        (1, 'Parallel Exec', ['40 workers', 'Async'], GCP_BLUE),
        (3, 'Retry Logic', ['Exp. backoff', '3 attempts'], GCP_GREEN),
        (5, 'SQL Eval', ['Exact match', 'Semantic'], GCP_RED),
        (7, 'Aggregation', ['Mean ± Std', 'Statistics'], GCP_YELLOW),
        (9, 'Failure Scan', ['Root cause', 'Patterns'], GCP_RED),
        (11, 'Validation', ['Prompt check', 'Size limits'], GCP_YELLOW),
        (13.2, 'Rollback', ['Detect regress', 'Restore'], GCP_GREEN),
    ]

    for x_pos, title, items, color in eval_boxes:
        create_component_box(ax, (x_pos, y_eval - 0.7), 1.8, 1.0,
                            title, items, color)

    # ===== ARROWS (Clean routing, no overlaps) =====
    # UI to Orchestration (separate paths, no overlap)
    create_clean_arrow(ax, (2, y_ui - 0.9), (2.5, y_orch + 0.3), GCP_GREEN, '① Deploy', lw=2)
    create_clean_arrow(ax, (5.6, y_ui - 0.9), (5.6, y_orch + 0.3), GCP_BLUE, '② Optimize', lw=2)

    # Orchestration to GCP (single vertical arrow, centered)
    create_clean_arrow(ax, (4, y_orch - 1.3), (4, y_gcp + 0.5), GCP_BLUE, '③ Query & Deploy', lw=2.5)

    # GCP to Evaluation (single vertical arrow)
    create_clean_arrow(ax, (4, y_gcp - 2.3), (7, y_eval + 0.6), GCP_BLUE, '④ Results', lw=2.5)

    # Evaluation to Orchestration (feedback loop - far left to avoid overlap)
    ax.annotate('', xy=(0.8, y_orch - 1.3), xytext=(0.8, y_eval + 0.6),
                arrowprops=dict(arrowstyle='->', color=GCP_YELLOW, lw=3,
                               connectionstyle="arc3,rad=0", alpha=0.8), zorder=1)
    ax.text(0.4, 5, '⑤ Feedback\nLoop', rotation=90, va='center', ha='center',
            fontsize=8, color=GCP_YELLOW, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.4', facecolor=WHITE, edgecolor=GCP_YELLOW, linewidth=2),
            zorder=5)

    # ===== LEGEND =====
    legend_elements = [
        mpatches.Patch(facecolor=GCP_BLUE, edgecolor=GCP_BLUE, label='Core Services'),
        mpatches.Patch(facecolor=GCP_RED, edgecolor=GCP_RED, label='AI/ML Engines'),
        mpatches.Patch(facecolor=GCP_GREEN, edgecolor=GCP_GREEN, label='Deploy & Auth'),
        mpatches.Patch(facecolor=GCP_YELLOW, edgecolor=GCP_YELLOW, label='Analysis'),
    ]

    ax.legend(handles=legend_elements, loc='upper right',
              frameon=True, facecolor=WHITE, edgecolor=CLOUD_GRAY,
              fontsize=8, ncol=4, columnspacing=1)

    # ===== FOOTER =====
    ax.text(10, 0.35, 'Data Insights Agent Test Harness v2.0  |  Iterative Optimization Framework',
            ha='center', fontsize=9, color=CLOUD_GRAY, style='italic',
            family='sans-serif')

    # Save
    plt.tight_layout()
    plt.savefig('docs/architecture_diagram.png', dpi=300, bbox_inches='tight',
                facecolor=BACKGROUND, edgecolor='none')
    print("✓ Architecture diagram saved to: docs/architecture_diagram.png")

    # High-res version for printing
    plt.savefig('docs/architecture_diagram_highres.png', dpi=600, bbox_inches='tight',
                facecolor=BACKGROUND, edgecolor='none')
    print("✓ High-res diagram saved to: docs/architecture_diagram_highres.png")

    plt.close()

if __name__ == '__main__':
    main()
