import html
import json


def render_dashboard(metrics: dict, recent_requests: list[dict], hourly_stats: list[dict]) -> str:
    """
    Renders a server-side HTML dashboard for the customer support API.

    Args:
        metrics: Dictionary containing overall metrics (total_requests, avg_latency_ms, resolution_rate, total_estimated_cost_usd).
        recent_requests: List of dictionaries representing recent requests.
        hourly_stats: List of dictionaries with hourly stats for charts (hour, count, avg_latency).

    Returns:
        A string containing the complete HTML page.
    """
    # Handle defaults
    total_requests = metrics.get('total_requests', 0)
    avg_latency = metrics.get('avg_latency_ms', 0.0)
    resolution_rate = metrics.get('resolution_rate', 0.0)
    total_cost = metrics.get('total_estimated_cost_usd', 0.0)

    # Prepare chart data
    hours = [stat.get('hour', '') for stat in hourly_stats]
    request_counts = [stat.get('count', 0) for stat in hourly_stats]
    avg_latencies = [stat.get('avg_latency', 0.0) for stat in hourly_stats]

    chart_data_js = f"""
    const hours = {json.dumps(hours)};
    const requestCounts = {json.dumps(request_counts)};
    const avgLatencies = {json.dumps(avg_latencies)};
    """

    # Table rows
    table_rows = ""
    for req in recent_requests[:10]:
        ts = html.escape(str(req.get('timestamp', '')))
        cust_id = html.escape(str(req.get('customer_id', '')))
        query = str(req.get('query', ''))
        query_truncated = html.escape(query[:50] + ('...' if len(query) > 50 else ''))
        category = html.escape(str(req.get('category', '')))
        agent = html.escape(str(req.get('agent', '')))
        latency = req.get('latency_ms', 0)
        cost = req.get('estimated_cost_usd', 0.0)
        
        table_rows += f"""
        <tr>
            <td>{ts}</td>
            <td>{cust_id}</td>
            <td title="{html.escape(query)}">{query_truncated}</td>
            <td>{category}</td>
            <td>{agent}</td>
            <td>{latency} ms</td>
            <td>${cost:.4f}</td>
        </tr>
        """

    if not table_rows:
        table_rows = "<tr><td colspan='7' style='text-align:center;'>No recent requests found</td></tr>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Customer Support Dashboard &mdash; LLMOps Week 7</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-dark: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.8);
            --accent-purple: #8b5cf6;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --text-white: #f1f5f9;
            --text-muted: #94a3b8;
            --border-color: rgba(255, 255, 255, 0.1);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', sans-serif;
        }}

        body {{
            background-color: var(--bg-dark);
            color: var(--text-white);
            padding: 2rem;
            min-height: 100vh;
        }}

        h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 2rem;
            background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
        }}

        .dashboard-container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .glass-card {{
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            animation: fadeInUp 0.6s ease-out forwards;
            opacity: 0;
            transform: translateY(20px);
        }}

        @keyframes fadeInUp {{
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        /* Staggered animation */
        .summary-grid .glass-card:nth-child(1) {{ animation-delay: 0.1s; }}
        .summary-grid .glass-card:nth-child(2) {{ animation-delay: 0.2s; }}
        .summary-grid .glass-card:nth-child(3) {{ animation-delay: 0.3s; }}
        .summary-grid .glass-card:nth-child(4) {{ animation-delay: 0.4s; }}
        .charts-grid .glass-card:nth-child(1) {{ animation-delay: 0.5s; }}
        .charts-grid .glass-card:nth-child(2) {{ animation-delay: 0.6s; }}
        .table-container {{ animation-delay: 0.7s; }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .summary-card h3 {{
            font-size: 1rem;
            color: var(--text-muted);
            font-weight: 500;
            margin-bottom: 0.5rem;
        }}

        .summary-card p {{
            font-size: 2rem;
            font-weight: 700;
        }}

        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .chart-wrapper {{
            position: relative;
            height: 300px;
            width: 100%;
        }}
        
        .chart-title {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-white);
        }}

        .table-container {{
            overflow-x: auto;
        }}

        .table-title {{
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-white);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th, td {{
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
        }}

        th {{
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.05em;
        }}

        tr {{
            transition: background-color 0.2s ease;
        }}

        tr:hover td {{
            background-color: rgba(255, 255, 255, 0.05);
        }}
        
        @media (max-width: 768px) {{
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="dashboard-container">
        <h1>Customer Support Dashboard &mdash; LLMOps Week 7</h1>
        
        <div class="summary-grid">
            <div class="glass-card summary-card">
                <h3>Total Requests</h3>
                <p>{total_requests}</p>
            </div>
            <div class="glass-card summary-card">
                <h3>Avg Latency</h3>
                <p>{avg_latency:.1f} ms</p>
            </div>
            <div class="glass-card summary-card">
                <h3>Resolution Rate (non-escalated)</h3>
                <p>{resolution_rate:.1f}%</p>
            </div>
            <div class="glass-card summary-card">
                <h3>Est. Total Cost</h3>
                <p>{total_cost:.4f} USD</p>
            </div>
        </div>

        <div class="charts-grid">
            <div class="glass-card">
                <div class="chart-title">Requests Over Time</div>
                <div class="chart-wrapper">
                    <canvas id="requestsChart"></canvas>
                </div>
            </div>
            <div class="glass-card">
                <div class="chart-title">Average Latency Over Time</div>
                <div class="chart-wrapper">
                    <canvas id="latencyChart"></canvas>
                </div>
            </div>
        </div>

        <div class="glass-card table-container">
            <div class="table-title">Recent Requests</div>
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Customer ID</th>
                        <th>Query</th>
                        <th>Category</th>
                        <th>Agent</th>
                        <th>Latency</th>
                        <th>Est. Cost</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        {chart_data_js}

        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Inter', sans-serif";
        
        // Helper to create gradient
        function createGradient(ctx, colorStart, colorEnd) {{
            const gradient = ctx.createLinearGradient(0, 0, 0, 300);
            gradient.addColorStop(0, colorStart);
            gradient.addColorStop(1, colorEnd);
            return gradient;
        }}

        // Requests Chart
        const reqCtx = document.getElementById('requestsChart').getContext('2d');
        const reqGradient = createGradient(reqCtx, 'rgba(139, 92, 246, 0.5)', 'rgba(139, 92, 246, 0.05)');
        
        new Chart(reqCtx, {{
            type: 'line',
            data: {{
                labels: hours,
                datasets: [{{
                    label: 'Request Count',
                    data: requestCounts,
                    borderColor: '#8b5cf6',
                    backgroundColor: reqGradient,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#8b5cf6',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: '#8b5cf6'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: 'rgba(255, 255, 255, 0.1)' }}
                    }},
                    x: {{
                        grid: {{ display: false }}
                    }}
                }}
            }}
        }});

        // Latency Chart
        const latCtx = document.getElementById('latencyChart').getContext('2d');
        const latGradient = createGradient(latCtx, 'rgba(59, 130, 246, 0.5)', 'rgba(59, 130, 246, 0.05)');

        new Chart(latCtx, {{
            type: 'line',
            data: {{
                labels: hours,
                datasets: [{{
                    label: 'Avg Latency (ms)',
                    data: avgLatencies,
                    borderColor: '#3b82f6',
                    backgroundColor: latGradient,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#3b82f6',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: '#3b82f6'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        grid: {{ color: 'rgba(255, 255, 255, 0.1)' }}
                    }},
                    x: {{
                        grid: {{ display: false }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""
    return html_content
