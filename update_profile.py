"""Regenerate dark_mode.svg / light_mode.svg with live GitHub stats.

Runs daily via GitHub Actions. Stdlib only, no external dependencies.
"""
import calendar
import html
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# Profile Configuration
# ─────────────────────────────────────────────────────────────────────────────
USER = "duoyuli"
JOINED_DATE = date(2016, 3, 10)  # GitHub registration date (or replace with BIRTHDAY)
JOINED_YEAR = JOINED_DATE.year
W = 62  # info column width in characters

OS_INFO = "macOS"
HOST = "Apple Silicon"
KERNEL = "Software Engineer"
IDE = "Claude Code, Codex, Zed, IDEA, CLion"

LANG_PROG = "Java, Rust, Go, TypeScript, Python"
LANG_REAL = "Chinese (Primary), English (Little)"
HOBBIES = "Agent Orchestration, Quant"

EMAIL = "liweichao0102@gmail.com"
TWITTER = "@duoyuli_x"
GITHUB_URL = f"github.com/{USER}"

ART = r"""
            .   ::.
             :+*%%#*-
            =%%%%%%%%*
            %%%%%###%#+
            %%%%%%%%%%#:
         - +%%%%%%%%%%@.        ...::-==+-
         - +@%%%%%#+##-:+******##########*
         = +@%%%%+=-*= -#*##********#####+
         . ==-*#-==.-  -#**####****######+
         --=:--::--..  =%**####****######=
.=+:.++-+*++++=::=-: . =#****##**#######%=
:--.:-+++=====-..==  =-+%***############%-
.::==+=--=---==-.    =+*%***####****####%-
 :=+++=+=--=++--=--: =++%***###****#*####-
.====-++===++==+=+==. +*################%-
+***+++======+++*+--: .+==***#####*****#=.
%%%%%%##++=+*+=+*===:. :::#*######***#-: .
#%%%%%%%*#+=**+*+==+**+.-=#*##*###****----
*%%%%%%%%%#+++*#*==*+=: -***######*##*===-
*##%%%%%%##++*+**=*+-==-:=***#####**#+--=-
+##%#%%%%%%+=+#**++--==----  :+######=::..
=###%%%%%%%#++*##+++++=+*-.   +#***+*=--=.
+#**%%%%%%%%+*#*##++*+=+++= .*-.=+-==-+++:
=****#%%%%%%+++*%##**++++*+-=+:::    ..  .
-****#%##%%%*+*#*#=******++*+
.=++**###%%##****+:*@%%#**##:
 -==+++**#%#%*+***=+#%%%###*-:..         =
  :--:==+*###++==+***#**###%%#**++--:  =-
"""

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN") or ""
PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN
DIR = os.path.dirname(os.path.abspath(__file__))


def gh_request(url, payload=None, token=None, retries=3):
    headers = {
        "Authorization": f"Bearer {token or TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": f"github-profile-{USER}",
    }
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=headers)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or "{}")
        except urllib.error.HTTPError as e:
            if e.code in (500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def graphql(query, variables=None, token=None):
    _, resp = gh_request(
        "https://api.github.com/graphql",
        {"query": query, "variables": variables or {}},
        token=token,
    )
    if resp.get("errors"):
        raise RuntimeError(resp["errors"])
    return resp["data"]


def age(b, t):
    years = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    months = (t.month - b.month - (t.day < b.day)) % 12
    if t.day >= b.day:
        days = t.day - b.day
    else:
        pm_year, pm = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        days = calendar.monthrange(pm_year, pm)[1] - b.day + t.day
    return years, months, days


def fetch_stats():
    now_year = datetime.now(timezone.utc).year
    yr_aliases = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y + 1}-01-01T00:00:00Z")'
        " { totalCommitContributions restrictedContributionsCount }"
        for y in range(JOINED_YEAR, now_year + 1)
    )
    contrib = graphql(f'query {{ user(login: "{USER}") {{ {yr_aliases} }} }}')["user"]
    commits = sum(
        v["totalCommitContributions"] + v["restrictedContributionsCount"]
        for v in contrib.values()
    )
    u = graphql(f"""
    query {{
      user(login: "{USER}") {{
        id
        followers {{ totalCount }}
        repositories(first: 100, ownerAffiliations: OWNER) {{
          totalCount
          nodes {{ name stargazerCount isFork isPrivate }}
        }}
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {{
          totalCount
        }}
      }}
    }}""", token=PRIV_TOKEN)["user"]
    stats = {
        "followers": u["followers"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in u["repositories"]["nodes"]),
        "commits": commits,
    }
    stats.update(loc([n["name"] for n in u["repositories"]["nodes"] if not n["isFork"]], u["id"]))
    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 30, author: {id: $id}, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def loc(repo_names, user_id):
    add = rem = 0
    for name in repo_names:
        cursor = None
        print(f"walking LOC for {name}...")
        try:
            while True:
                ref = graphql(
                    LOC_QUERY,
                    {"owner": USER, "name": name, "id": user_id, "cursor": cursor},
                    token=PRIV_TOKEN,
                )["repository"]["defaultBranchRef"]
                if ref is None:
                    break
                h = ref["target"]["history"]
                add += sum(n["additions"] for n in h["nodes"])
                rem += sum(n["deletions"] for n in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                cursor = h["pageInfo"]["endCursor"]
        except Exception as e:
            print(f"loc {name}: {e}")
    return {"loc_add": add, "loc_del": rem, "loc": add - rem}


PALETTES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "art": "#8b949e", "h": "#58a6ff",
             "k": "#ffa657", "v": "#c9d1d9", "d": "#484f58", "g": "#3fb950", "r": "#f85149"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "art": "#57606a", "h": "#0969da",
              "k": "#953800", "v": "#24292f", "d": "#afb8c1", "g": "#1a7f37", "r": "#cf222e"},
}


def kv(key, val, width=W):
    dots = "." * max(width - len(key) - len(str(val)) - 3, 1)
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(val), "v")]


def kv2(k1, v1, k2, v2):
    left = kv(k1, v1, 33)
    return left + [(" | ", "d")] + kv(k2, v2, 26)


def rule(title=""):
    label = f"─ {title} " if title else ""
    return [(label, "h"), ("─" * (W - len(label)), "d")]


def info_lines(s):
    y, m, d = age(JOINED_DATE, date.today())
    n = lambda x: f"{x:,}"
    return [
        [(f"{USER.lower()}@github ", "h"), ("─" * (W - len(USER) - 8), "d")],
        [],
        kv("OS", OS_INFO),
        kv("Uptime", f"{y} years, {m} months, {d} days"),
        kv("Host", HOST),
        kv("Kernel", KERNEL),
        kv("IDE", IDE),
        [],
        kv("Languages.Programming", LANG_PROG),
        kv("Languages.Real", LANG_REAL),
        kv("Hobbies", HOBBIES),
        [],
        rule("Contact"),
        kv("Email", EMAIL),
        kv("Twitter / X", TWITTER),
        kv("GitHub", GITHUB_URL),
        [],
        rule("GitHub Stats"),
        kv2("Repos", f"{s['repos']} {{Contributed: {s['contributed']}}}", "Stars", n(s["stars"])),
        kv2("Commits", n(s["commits"]), "Followers", n(s["followers"])),
        [("Lines of Code: ", "k"), (n(s["loc"]), "v"), (" ( ", "d"),
         (n(s["loc_add"]) + "++", "g"), (", ", "d"), (n(s["loc_del"]) + "--", "r"), (" )", "d")],
    ]


def render(mode, stats):
    p = PALETTES[mode]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="870" height="520" viewBox="0 0 870 520" '
        'font-family="Consolas, Menlo, monospace" font-size="13px">',
        f'<rect x="0.5" y="0.5" width="869" height="519" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]
    for i, line in enumerate(ART.strip("\n").split("\n")):
        out.append(f'<text x="25" y="{42 + i * 16}" fill="{p["art"]}" xml:space="preserve">{html.escape(line)}</text>')
    for i, segs in enumerate(info_lines(stats)):
        if not segs:
            continue
        spans = "".join(f'<tspan fill="{p[c]}">{html.escape(t)}</tspan>' for t, c in segs)
        out.append(f'<text x="370" y="{42 + i * 21}" xml:space="preserve">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    stats = fetch_stats()
    print("Fetched stats:", stats)
    for mode in PALETTES:
        svg_path = os.path.join(DIR, f"{mode}_mode.svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(render(mode, stats))
    print("Wrote dark_mode.svg and light_mode.svg successfully")
