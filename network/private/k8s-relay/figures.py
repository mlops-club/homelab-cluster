# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib", "diagrams"]
# ///
"""
figures.py

Purpose: Render the benchmark plots and architecture diagram embedded in README.md

Scope: Documentation assets only (images/*.png)

Overview: Holds the measured benchmark results as constants (single HTTP stream from a Lightsail
    client in us-east-2 to a host on the home LAN) and renders three plots with matplotlib plus an
    architecture diagram with the `diagrams` library. Re-run after re-benchmarking.

Dependencies: matplotlib, diagrams (requires Graphviz `dot` on PATH)

Exports: images/throughput.png, images/failover.png, images/relay-size.png, images/architecture.png

Interfaces: uv run figures.py

Implementation: One neutral color for baseline paths, one accent for paths through k8s-relay
"""

from pathlib import Path

import matplotlib.pyplot as plt

OUT = Path(__file__).parent / "images"

SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#a3a29c", "#e6e5e1"
ACCENT = "#2a78d6"  # paths through k8s-relay
BASE = "#8c8b85"  # everything else

# Mbit/s, three 20 s runs each (nano: one 180 s sustained run, reported as its 15 s averages' range).
THROUGHPUT = [
    ("Direct UDP", [102.5, 142.8, 130.6], False),
    ("Tailscale DERP", [21.2, 22.5, 22.1], False),
    ("Funnel", [21.4, 21.6, 21.1, 19.9, 21.1, 21.6], False),
    ("Funnel + relay up", [7.1, 6.0, 21.0, 7.6, 0.9, 7.9], False),
    ("Relay: nano_3_0 (3 min)", [26.5], True),
    ("Relay: large_3_0", [151.5, 149.9, 176.1], True),
]

# (seconds, Mbit/s) per one-second bucket; relay UDP blackholed at t=30.3 s.
FAILOVER = [(1.0,66),(2.0,165),(3.1,166),(4.1,176),(5.1,180),(6.1,182),(7.1,185),(8.1,188),(9.1,190),(10.1,186),(11.1,182),(12.2,184),(13.2,155),(14.2,150),(15.2,159),(16.2,171),(17.2,179),(18.2,184),(19.2,181),(20.2,188),(21.2,189),(22.2,191),(23.2,184),(24.2,188),(25.2,190),(26.2,189),(27.2,186),(28.2,196),(29.2,204),(30.3,209),(31.3,0),(37.2,0),(38.2,15),(39.2,23),(40.2,23),(41.2,23),(42.2,23),(43.2,23),(44.3,23),(45.5,16),(46.5,12),(47.6,14),(48.7,11),(49.8,10),(50.9,12),(51.9,16),(52.9,21),(54.0,23),(55.0,23),(56.0,23),(57.0,23),(58.0,23),(59.0,23),(60.1,23),(61.1,23),(62.1,23),(63.2,23),(64.2,23),(65.2,23),(66.2,23),(67.2,23),(68.2,23),(69.2,23),(70.2,23),(71.3,23),(72.3,23),(73.3,23),(74.3,23),(75.3,23),(76.4,16),(77.5,23),(78.6,15),(79.6,10),(80.7,11),(81.8,16),(82.9,15),(84.0,17),(85.1,19),(86.1,23),(87.1,23),(88.1,23),(89.1,23),(90.1,23)]  # fmt: skip

# (seconds, Mbit/s) nano_3_0 relay, sustained download.
NANO = [(1.1,39),(2.2,72),(3.2,44),(4.3,32),(5.3,34),(6.4,36),(7.4,30),(8.5,24),(9.5,24),(10.6,26),(11.6,26),(12.7,26),(13.7,26),(14.8,20),(15.8,16),(16.9,8),(18.0,10),(19.0,16),(20.1,16),(21.2,17),(22.2,18),(23.3,20),(24.3,22),(25.4,23),(26.5,23),(27.6,19),(28.7,21),(29.7,23),(30.8,24),(31.8,24),(32.9,24),(33.9,26),(35.0,28),(36.0,30),(37.1,32),(38.1,34),(39.1,41),(40.2,50),(41.2,54),(42.2,50),(43.2,52),(44.2,44),(45.3,46),(46.3,48),(47.3,48),(48.4,49),(49.4,48),(50.4,50),(51.4,52),(52.5,43),(53.5,35),(54.5,34),(55.6,35),(56.6,35),(57.6,33),(58.6,29),(59.7,33),(60.7,36),(61.7,36),(62.8,37),(63.8,29),(64.9,32),(65.9,29),(67.0,25),(68.0,18),(69.1,17),(70.1,18),(71.2,19),(72.3,15),(73.3,18),(74.3,18),(75.5,15),(76.5,14),(77.7,13),(78.8,14),(79.9,15),(81.0,17),(82.1,15),(83.2,15),(84.3,13),(85.4,12),(86.5,10),(87.7,8),(88.9,9),(89.9,10),(91.1,11),(92.2,14),(93.2,15),(94.3,17),(95.4,19),(96.4,21),(97.5,19),(98.5,19),(99.6,22),(100.7,22),(101.7,23),(102.7,23),(103.7,20),(104.7,20),(105.7,23),(106.8,24),(107.8,24),(108.9,24),(110.0,25),(111.0,27),(112.0,29),(113.0,31),(114.0,21),(115.1,15),(116.2,15),(117.3,16),(118.4,17),(119.4,19),(120.4,21),(121.5,23),(122.5,25),(123.5,26),(124.5,28),(125.6,33),(126.6,41),(127.7,49),(128.7,37),(129.7,35),(130.8,36),(131.8,37),(132.8,37),(133.8,38),(134.8,40),(135.8,42),(136.8,33),(137.9,37),(138.9,29),(140.0,31),(141.0,32),(142.0,27),(143.1,20),(144.1,20),(145.1,21),(146.2,22),(147.2,23),(148.2,25),(149.2,26),(150.3,23),(151.4,26),(152.4,27),(153.4,21),(154.4,16),(155.5,18),(156.6,18),(157.7,19),(158.8,21),(159.8,24),(160.8,25),(161.8,27),(162.9,29),(163.9,24),(164.9,26),(166.0,29),(167.0,30),(168.1,30),(169.1,30),(170.1,31),(171.2,31),(172.3,28),(173.3,28),(174.4,29),(175.5,26),(176.5,25),(177.6,22),(178.6,22),(179.7,20)]  # fmt: skip

DERP_MBIT, LARGE_MBIT = 22, 159  # medians, for reference lines


def style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=13, fontweight="semibold", pad=12)
    ax.set_xlabel(xlabel, color=INK_2)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.tick_params(colors=INK_2, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)


def figure(width: float = 9, height: float = 4.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def throughput() -> None:
    fig, ax = figure(9, 4.4)
    rows = list(reversed(THROUGHPUT))
    for y, (label, runs, relay) in enumerate(rows):
        median = sorted(runs)[len(runs) // 2]
        color = ACCENT if relay else BASE
        ax.barh(y, median, height=0.6, color=color)
        if len(runs) > 1:
            ax.plot([min(runs), max(runs)], [y, y], color=INK, lw=1.2)
        ax.text(max(runs) + 3, y, f"{median:.0f}", va="center", color=INK, fontsize=10)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], color=INK)
    ax.xaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_xlim(0, 200)
    style(ax, "Download throughput by path (median; line = min to max)", "Mbit/s", "")
    fig.tight_layout()
    fig.savefig(OUT / "throughput.png", facecolor=SURFACE)


def failover() -> None:
    fig, ax = figure()
    xs, ys = zip(*FAILOVER)
    ax.plot(xs, ys, color=ACCENT, lw=2)
    ax.axvline(30.3, color=INK_2, lw=1, ls="--")
    ax.annotate("relay blackholed", (30.3, 205), xytext=(34, 200), color=INK_2, fontsize=10)
    ax.annotate("7.4 s stall, then DERP\n(same TCP connection)", (38.2, 15), xytext=(45, 80),
                color=INK, fontsize=10, arrowprops={"arrowstyle": "-", "color": MUTED})
    ax.yaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 230)
    style(ax, "Relay failure mid-download falls back to DERP", "seconds", "Mbit/s")
    fig.tight_layout()
    fig.savefig(OUT / "failover.png", facecolor=SURFACE)


def relay_size() -> None:
    fig, ax = figure()
    xs, ys = zip(*NANO)
    ax.plot(xs, ys, color=ACCENT, lw=2)
    for level, text in ((LARGE_MBIT, "large_3_0 relay (median)"), (DERP_MBIT, "Tailscale DERP")):
        ax.axhline(level, color=INK_2, lw=1, ls="--")
        ax.text(181, level, f" {text}", va="center", color=INK_2, fontsize=10)
    ax.text(60, 62, "nano_3_0 relay", color=INK, fontsize=10)
    ax.yaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 180)
    ax.set_xlim(0, 180)
    style(ax, "A nano relay drains its network burst and settles near DERP speed", "seconds", "Mbit/s")
    fig.tight_layout()
    fig.savefig(OUT / "relay-size.png", facecolor=SURFACE)


def architecture() -> None:
    from diagrams import Cluster, Diagram, Edge
    from diagrams.aws.compute import Lightsail
    from diagrams.generic.network import Firewall
    from diagrams.k8s.infra import Node
    from diagrams.onprem.client import Client
    from diagrams.onprem.network import Internet

    graph = {"pad": "0.4", "nodesep": "0.7", "ranksep": "1.1", "fontsize": "13", "bgcolor": SURFACE}
    with Diagram("", filename=str(OUT / "architecture"), outformat="png", show=False, direction="LR", graph_attr=graph):
        with Cluster("Away from home"):
            device = Client("laptop / phone\n(UDP-hostile network)")
        with Cluster("AWS Lightsail us-west-2"):
            relay = Lightsail("k8s-relay\nUDP 40000")
        derp = Internet("Tailscale DERP\n(shared, ~22 Mbit/s)")
        with Cluster("Home (gigabit, easy NAT)"):
            router = Firewall("router\nUPnP / NAT-PMP")
            nodes = [Node(f"cluster-node-{i}") for i in (1, 2, 3)]
        device >> Edge(label="1. direct UDP", style="dashed", color=MUTED) >> router
        device >> Edge(label="2. peer relay ~160 Mbit/s", color=ACCENT, penwidth="2") >> relay
        relay >> Edge(color=ACCENT, penwidth="2") >> router
        device >> Edge(label="3. fallback", color=BASE) >> derp >> Edge(color=BASE) >> router
        router >> nodes


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"
    throughput()
    failover()
    relay_size()
    architecture()
