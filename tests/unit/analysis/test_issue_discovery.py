from app.analysis.issue_discovery import IssueDiscoverer


def test_discover_issue_header_roman():
    text = """
    II. Standing

    The court must first address jurisdiction. In [123 U.S. 456], the Supreme Court held...
    """
    citation = "123 U.S. 456"
    discoverer = IssueDiscoverer()
    result = discoverer.discover_issue(text, citation)
    assert result["label"] == "Standing"
    assert result["source"] == "auto_discovered_header"


def test_discover_issue_header_word():
    text = """
    DISCUSSION

    We turn now to the merits. See [123 U.S. 456].
    """
    citation = "123 U.S. 456"
    discoverer = IssueDiscoverer()
    result = discoverer.discover_issue(text, citation)
    assert result["label"] == "Discussion"
    assert result["source"] == "auto_discovered_header"


def test_discover_issue_keyword():
    text = "Regarding the issue of privacy, the court held in [123 U.S. 456] that..."
    citation = "123 U.S. 456"
    discoverer = IssueDiscoverer()
    result = discoverer.discover_issue(text, citation)
    assert result["label"] == "Privacy"
    assert result["source"] == "auto_discovered_keyword"


def test_discover_issue_fallback():
    text = "Just some random text with [123 U.S. 456] citation."
    citation = "123 U.S. 456"
    discoverer = IssueDiscoverer()
    result = discoverer.discover_issue(text, citation)
    assert result["label"] == "General Application"
    assert result["source"] == "fallback"
