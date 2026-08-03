"""
GitHub Contribution Grid SVG Generator
=======================================
Fetches the public contributions page from GitHub
(https://github.com/users/<user>/contributions), extracts the exact
data-level (0-4) and contribution count for every day, and renders an
SVG that mirrors the GitHub contribution calendar precisely.

No authentication needed — the page is public.
"""

import urllib.request, re, datetime, os

USERNAME = "MahdiRaahimi"

# GitHub dark-theme calendar colors (official Primer palette)
LEVEL_COLORS = {
    0: "#161b22",
    1: "#0e4429",
    2: "#006d32",
    3: "#26a641",
    4: "#39d353",
}


def fetch_contribution_days():
    """
    Fetch the HTML contributions page and return an ordered dict:
        date_str -> (level, count)

    The page renders <td> elements in row-major order:
    row 0 = all Sundays, row 1 = all Mondays, ..., row 6 = all Saturdays.
    Each <td> is followed by a <tool-tip> that says either
    "No contributions on ..." or "N contributions on ...".
    """
    url = "https://github.com/users/%s/contributions" % USERNAME

    # Use curl to fetch the page — more reliable than urllib on Windows
    import subprocess, tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="wb")
    tmp.close()
    try:
        subprocess.run(
            ["curl", "-sL", "--max-time", "60",
             "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
             "-H", "Accept: text/html",
             "-o", tmp.name, url],
            check=True, timeout=90
        )
        with open(tmp.name, "r", encoding="utf-8") as f:
            page = f.read()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    if not page:
        raise RuntimeError("Failed to fetch contributions page")

    # Extract date + level from each <td>
    day_re = re.compile(
        r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*?data-level="(\d)"'
    )
    days = day_re.findall(page)

    # Extract counts from tooltips (same order as days)
    tooltip_re = re.compile(
        r'>(?:No contributions|(\d+)\s+contributions?)\s+on\s+'
    )
    tooltips = tooltip_re.findall(page)

    day_data = {}
    for i, (date_str, level_str) in enumerate(days):
        count = int(tooltips[i]) if i < len(tooltips) and tooltips[i] else 0
        day_data[date_str] = (int(level_str), count)

    return day_data


def build_weeks(day_data):
    """
    Convert the date→(level,count) dict into a column-major grid:
    weeks[week_index][day_of_week] = {date, level, count}

    GitHub's calendar starts on the Sunday of the week containing the
    first day, and ends on the Saturday of the last week.
    """
    if not day_data:
        return []

    sorted_dates = sorted(day_data.keys())
    first_date = datetime.date.fromisoformat(sorted_dates[0])
    last_date = datetime.date.fromisoformat(sorted_dates[-1])

    # Align start to Sunday (weekday() returns Mon=0..Sun=6)
    start = first_date - datetime.timedelta(days=(first_date.weekday() + 1) % 7)

    weeks = []
    total_contribs = 0
    active_days = 0
    max_count = 0
    current = start
    while current <= last_date:
        week = []
        for _ in range(7):
            ds = current.isoformat()
            if ds in day_data:
                level, count = day_data[ds]
            else:
                level, count = 0, 0
            week.append({"date": ds, "level": level, "count": count})
            total_contribs += count
            if count > 0:
                active_days += 1
                max_count = max(max_count, count)
            current += datetime.timedelta(days=1)
        weeks.append(week)

    return weeks, total_contribs, active_days, max_count


def generate_svg(weeks, total_contribs, active_days, max_count):
    cell_size = 11
    cell_gap = 3
    margin_left = 30
    margin_top = 45
    svg_width = margin_left + len(weeks) * (cell_size + cell_gap) + 10
    svg_height = margin_top + 7 * (cell_size + cell_gap) + 30

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_positions = {}
    for w_idx, week in enumerate(weeks):
        if week:
            month = int(week[0]["date"][5:7])
            if month not in month_positions:
                month_positions[month] = margin_left + w_idx * (cell_size + cell_gap)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (svg_width, svg_height, svg_width, svg_height),
        '<rect width="%d" height="%d" fill="#0d1117" rx="8"/>'
        % (svg_width, svg_height),
    ]

    # Title
    parts.append('<g font-family="Segoe UI, Arial, sans-serif">')
    parts.append('<text x="15" y="22" font-size="13" font-weight="600" fill="#c9d1d9">'
                 '%d contributions in the last year</text>' % total_contribs)
    parts.append('</g>')

    # Stats
    parts.append('<g font-family="Segoe UI, Arial, sans-serif" font-size="11">')
    sx = 15
    sy = 35
    if active_days > 0:
        parts.append('<text x="%d" y="%d" fill="#39d353">Active: %d days</text>'
                     % (sx, sy, active_days))
        sx += 100
    if max_count > 0:
        parts.append('<text x="%d" y="%d" fill="#39d353">Max: %d in a day</text>'
                     % (sx, sy, max_count))
    parts.append('</g>')

    # Month labels
    parts.append('<g font-family="Segoe UI, Arial, sans-serif" font-size="10" fill="#8b949e">')
    for month, x in sorted(month_positions.items()):
        parts.append('<text x="%d" y="%d">%s</text>'
                     % (x, margin_top - 6, month_names[month - 1]))
    parts.append('</g>')

    # Day labels
    parts.append('<g font-family="Segoe UI, Arial, sans-serif" font-size="10" fill="#8b949e">')
    for day_idx, label in {1: "Mon", 3: "Wed", 5: "Fri"}.items():
        y = margin_top + day_idx * (cell_size + cell_gap) + cell_size - 1
        parts.append('<text x="2" y="%d">%s</text>' % (y, label))
    parts.append('</g>')

    # Cells — exact GitHub level→color mapping
    parts.append('<g>')
    for w_idx, week in enumerate(weeks):
        for d_idx, day in enumerate(week):
            x = margin_left + w_idx * (cell_size + cell_gap)
            y = margin_top + d_idx * (cell_size + cell_gap)
            color = LEVEL_COLORS.get(day["level"], "#161b22")
            parts.append('<rect x="%d" y="%d" width="%d" height="%d" rx="2" ry="2" fill="%s"/>'
                         % (x, y, cell_size, cell_size, color))
    parts.append('</g>')

    # Legend
    footer_y = svg_height - 12
    legend_x = svg_width - 190
    legend_colors = [LEVEL_COLORS[i] for i in range(5)]
    parts.append('<g font-family="Segoe UI, Arial, sans-serif" font-size="10" fill="#8b949e">')
    parts.append('<text x="%d" y="%d">Less</text>' % (legend_x - 25, footer_y))
    for i, c in enumerate(legend_colors):
        lx = legend_x + i * (cell_size + cell_gap)
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" rx="2" ry="2" fill="%s"/>'
                     % (lx, footer_y - 9, cell_size, cell_size, c))
    parts.append('<text x="%d" y="%d">More</text>'
                 % (legend_x + 5 * (cell_size + cell_gap) + 4, footer_y))
    parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    day_data = fetch_contribution_days()
    if not day_data:
        print("ERROR: No contribution data fetched")
        os.makedirs("dist", exist_ok=True)
        with open("dist/contribution-grid.svg", "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
                    '<text x="10" y="30" fill="#58a6ff">No data</text></svg>')
        return

    weeks, total, active, mx = build_weeks(day_data)
    svg = generate_svg(weeks, total, active, mx)
    os.makedirs("dist", exist_ok=True)
    with open("dist/contribution-grid.svg", "w") as f:
        f.write(svg)
    print("Generated SVG: %d bytes, %d weeks, %d total contributions, %d active days"
          % (len(svg), len(weeks), total, active))


if __name__ == "__main__":
    main()
