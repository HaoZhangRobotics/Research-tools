"""Fetch verified public full texts for specific 2025–2026 corpus gaps."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

from crawler import Paper, download_pdf
from enrich_author_corpus import abstract_from_pdf, introduction


ARXIV = {
    "continuous time state estimation methods in robotics a survey": "2411.03951",
    "building forest inventories with autonomous legged robots system lessons and challenges ahead": "2506.20315",
    "informed constrained aligned a field analysis on degeneracy aware point cloud registration in the wild": "2408.11809",
    "leva a high mobility logistic vehicle with legged suspension": "2503.10028",
    "learning quiet walking for a small home robot": "2502.10983",
    "dfm deep fourier mimic for expressive dance motion learning": "2502.10980",
    "dynamic object goal pushing with mobile manipulators through model free constrained reinforcement learning": "2502.01546",
    "residual policy learning for perceptive quadruped control using differentiable simulation": "2410.03076",
    "obstacle avoidant leader following with a quadruped robot": "2410.00572",
    "marladona towards cooperative team play using multi agent reinforcement learning": "2409.20326",
    "whole body end effector pose tracking": "2409.16048",
    "learning coordinated badminton skills for legged manipulators": "2505.22974",
    "risk guided diffusion toward deploying robot foundation models in space where failure is not an option": "2506.17601",
    "ros llm a framework for embodied ai": "2406.19741",
    "direction finding for software defined radios with switched uniform circular arrays": "2502.08592",
    "contact guided exploration for non prehensile locomanipulation with multi critic rl": "2608.28140",
    "task oriented robot human handovers on legged manipulators": "2602.05760",
    "tartanground a large scale dataset for ground robot perception and navigation": "2505.10696",
    "attention based map encoding for learning generalized legged locomotion": "2506.09588",
    "efficient model based reinforcement learning for robot control via online learning": "2510.18518",
}
DIRECT = {
    "generalized xr teleoperation toolkit for robotics": (
        "https://rffr.leggedrobotics.com/works/xr/IROS_WS_VR.pdf",
        "https://www.research-collection.ethz.ch/items/612a4584-8337-4e0e-8afa-274e914be919"),
    "lunarleaper a mission concept to explore the lunar subsurface with a small scale legged robot": (
        "https://elib.dlr.de/219586/1/1-s2.0-S0094576525008082-main.pdf",
        "https://www.lunarleaper.space/"),
    "spatially enhanced recurrent memory for long range mapless navigation via end to end reinforcement learning": (
        "https://www.research-collection.ethz.ch/bitstreams/0c5c40ce-d895-481b-aba5-ba85a3b7e140/download",
        "https://www.research-collection.ethz.ch/bitstreams/0c5c40ce-d895-481b-aba5-ba85a3b7e140/download"),
    "adaptive thresholding for sequence based place recognition": (
        "https://www.ipb.uni-bonn.de/wp-content/papercite-data/pdf/vysotska2025icra.pdf",
        "https://lamarr-institute.org/publication/adaptive-thresholding-for-sequence-based-place-recognition/"),
    "forestlpr lidar place recognition in forests attentioning multiple bev density images": (
        "https://openaccess.thecvf.com/content/CVPR2025/papers/Shen_ForestLPR_LiDAR_Place_Recognition_in_Forests_Attentioning_Multiple_BEV_Density_CVPR_2025_paper.pdf",
        "https://openaccess.thecvf.com/content/CVPR2025/html/Shen_ForestLPR_LiDAR_Place_Recognition_in_Forests_Attentioning_Multiple_BEV_Density_CVPR_2025_paper.html"),
    "robowrangler toward rope based grasping for mobile manipulation": (
        "https://mgomezandreu.github.io/personal/files/RoboWrangler.pdf",
        "https://www.research-collection.ethz.ch/entities/publication/cab69a66-454a-4723-83f8-a5436f706a7f"),
}
ETH_ITEMS = {
    "dual quadruped bimanual teleoperation with camera frame control": ("019e8fd6-3fa2-4cae-b898-8d034a3a1f36", "publication"),
    "lunarleaper from simulation to hardware for lunar legged locomotion": ("281b83fb-64c2-43a7-a9e3-932120cb0f1f", "publication"),
    "impulse free release mechanism and test setup for robotic free floating experiments on parabolic flights": ("4c646f7a-430c-4a80-8de7-22a71d2067eb", "publication"),
    "pace dataset for sim to real transfer in legged robots joint dynamics identification and locomotion experiments across multiple robot platforms": ("ea53e17a-76eb-460f-81ba-6e65f7078539", "researchdata"),
}


def eth_item(session, item_id):
    base = "https://www.research-collection.ethz.ch/server/api"
    response = session.get(f"{base}/core/items/{item_id}", timeout=25)
    response.raise_for_status()
    item = response.json()
    metadata = item.get("metadata", {})
    abstract_values = metadata.get("dc.description.abstract", [])
    abstract = " ".join(v.get("value", "") for v in abstract_values if v.get("value"))
    pdf_url = ""
    bundles_response = session.get(f"{base}/core/items/{item_id}/bundles?size=20", timeout=25)
    bundles_response.raise_for_status()
    for bundle in bundles_response.json().get("_embedded", {}).get("bundles", []):
        if bundle.get("name") != "ORIGINAL":
            continue
        href = bundle.get("_links", {}).get("bitstreams", {}).get("href")
        if not href:
            continue
        streams = session.get(href, timeout=25)
        streams.raise_for_status()
        for bitstream in streams.json().get("_embedded", {}).get("bitstreams", []):
            if bitstream.get("name", "").lower().endswith(".pdf"):
                pdf_url = bitstream.get("_links", {}).get("content", {}).get("href", "")
                if pdf_url:
                    break
        break
    return item, abstract, pdf_url


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def main(folder):
    root = Path(folder)
    path = root / "papers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers["User-Agent"] = "ResearchTools/1.0 (academic paper research)"
    lookups = {normalize(title): aid for title, aid in ARXIV.items()}
    lookups.update({normalize(title): urls for title, urls in DIRECT.items()})
    attempts = 0
    for item in data["papers"]:
        if item.get("year") not in (2025, 2026) or (item.get("abstract") and item.get("introduction")):
            continue
        key = normalize(item.get("title", ""))
        source = lookups.get(key)
        eth_source = ETH_ITEMS.get(key)
        if not source and not eth_source:
            # These are abstract-only records in public conference or dataset catalogs.
            if key == normalize("ARAMMIS: Autonomous Robots for Area Mapping, Monitoring and In-situ gas Sensing, focused on Lunar exploration and Earth Science applications"):
                item["abstract"] = ("The ARAMMIS project integrates a compact quadrupole mass spectrometer into a legged robot for autonomous 3D gas mapping, monitoring, and in-situ sampling in industrial, geological, and lunar-analog environments. The system autonomously controls the instrument and retrieves measurements. In June 2025, the team tested the modified ANYmal D at Mount Etna to characterize volcanic gas emissions in real time, demonstrating capabilities relevant to Earth science and future lunar exploration.")
                item["abstract_status"] = "摘要概述（根据 University of Pisa conference record，非原文）"
                item["source_url"] = "https://arpi.unipi.it/handle/11568/1324851"
                continue
            if key == normalize("PACE Dataset for Sim-to-Real Transfer in Legged Robots: Joint dynamics identification and locomotion experiments across multiple robot platforms."):
                eth_source = ETH_ITEMS.get(key)
            elif key == normalize("Can vervet monkeys learn from a robot?") or key == normalize("Culture Can vervet monkeys learn from a robot?"):
                item["abstract"] = ("Social learning—learning from others—is an important feature of primate cognition. Vervet monkeys socially learn from conspecifics, and this study asks whether they can also learn from a robot. A novel food-choice experiment in South Africa used a remotely controlled, sheep-sized ANYmal quadruped to test whether monkeys would follow the robot's food choices.")
                item["abstract_status"] = "会议摘要概述（根据 abstract booklet，非原文）"
                item["source_url"] = "https://culture-conference.com/wp-content/uploads/2025/01/abstract_booklet_pdf.pdf"
                continue
            if not eth_source:
                continue
        if eth_source:
            item_id, item_type = eth_source
            try:
                eth_record, eth_abstract, eth_pdf = eth_item(session, item_id)
                item["source_url"] = f"https://www.research-collection.ethz.ch/entities/{item_type}/{item_id}"
                if eth_abstract and not item.get("abstract"):
                    item["abstract"] = eth_abstract
                    item["abstract_status"] = "ETH Zurich Research Collection record"
                item["source_match"] = "题名匹配的 ETH Zurich Research Collection 条目"
                if eth_pdf:
                    item["pdf_url"] = eth_pdf
            except (requests.RequestException, ValueError, KeyError) as exc:
                item["eth_collection_status"] = f"公开 API 查询失败：{exc}"
                data["papers"] = data["papers"]
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                continue
        elif isinstance(source, tuple):
            item["pdf_url"], item["source_url"] = source
        else:
            item["pdf_url"] = f"https://arxiv.org/pdf/{source}"
            item["source_url"] = f"https://arxiv.org/abs/{source}"
        if not item.get("pdf_url"):
            attempts += 1
            continue
        paper = Paper(**{k: item.get(k, "") for k in Paper.__dataclass_fields__})
        download_pdf(paper, root / "pdfs", session=session)
        item.update({"pdf_url": paper.pdf_url, "pdf_file": paper.pdf_file,
                     "status": paper.status, "error": paper.error})
        if paper.pdf_file:
            pdf_path = Path(paper.pdf_file)
            abstract = abstract_from_pdf(pdf_path)
            intro = introduction(pdf_path)
            if abstract and not item.get("abstract"):
                item["abstract"] = abstract
                item["abstract_status"] = "已从核实的公开 PDF 首页抽取"
            if intro:
                item["introduction"] = intro
                item["intro_status"] = "已从核实的公开 PDF 抽取"
            item["source_match"] = "题名精确匹配的 arXiv/CVF/ETH Research Collection 公开来源"
        attempts += 1
        if attempts % 5 == 0:
            data["papers"] = data["papers"]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"verified sources processed: {attempts}; pdfs={sum(bool(x.get('pdf_file')) for x in data['papers'])}; intros={sum(bool(x.get('introduction')) for x in data['papers'] if x.get('year') in (2025, 2026))}", flush=True)
        time.sleep(0.8)
    papers = data["papers"]
    data["abstract_count"] = sum(bool(x.get("abstract")) for x in papers)
    data["downloaded"] = sum(bool(x.get("pdf_file")) for x in papers)
    data["introduction_count"] = sum(bool(x.get("introduction")) for x in papers)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"complete: sources={attempts}, 2025–26 abstracts={sum(bool(x.get('abstract')) for x in papers if x.get('year') in (2025, 2026))}, intros={sum(bool(x.get('introduction')) for x in papers if x.get('year') in (2025, 2026))}")


if __name__ == "__main__":
    main(sys.argv[1])
