import { useState } from 'react'

// Real Lambda Function URL (infra/mcp.tf's `mcp_function_url` output, path
// /mcp) -- public, no auth needed. Hardcoded rather than an env var since it
// only changes if the Lambda infra is ever torn down and recreated, which
// isn't a routine deploy-time event the way VITE_METADATA_BASE_URL is.
const MCP_URL = 'https://kije62pq2d6g6nxpkhx4afu7bm0yifuo.lambda-url.us-east-2.on.aws/mcp'

function CopyUrlButton() {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(MCP_URL)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Selecting the text manually still works if clipboard access fails.
    }
  }
  return (
    <button type="button" className="copy-context-button" onClick={handleCopy}>
      {copied ? 'Copied' : 'Copy URL'}
    </button>
  )
}

export default function McpAccessPage({ onBack }) {
  return (
    <div className="mcp-access-page">
      <button type="button" className="back-link" onClick={onBack}>&larr; Back to catalog</button>
      <h2>Connecting to the MCP server</h2>
      <p className="page-intro">
        This collection also has an MCP (Model Context Protocol) server --
        the same search/lookup tools this browser uses, available directly
        inside a Claude conversation. It doesn't transfer any file: it can
        only tell you where a study's processed data already lives (on HTCF and on RIS),
        not hand you a copy of it.
      </p>

      <div className="mcp-url-block">
        <span className="mcp-url-label">Server URL</span>
        <code className="mcp-url">{MCP_URL}</code>
        <CopyUrlButton />
      </div>

      <section className="mcp-connect-section">
        <h3>Claude.ai</h3>
        <ol>
          <li>Go to <strong>Settings &rarr; Connectors &rarr; Add custom connector</strong>.</li>
          <li>Paste the server URL above.</li>
          <li>Give it a name (e.g. "ALS Dataset Catalog").</li>
          <li>Click <strong>Add</strong>. No API key or other authentication is needed.</li>
        </ol>
      </section>

      <section className="mcp-connect-section">
        <h3>Claude Code (CLI)</h3>
        <p>Add it as a remote MCP server over HTTP:</p>
        <pre className="mcp-code-block">claude mcp add --transport http als-datasets {MCP_URL}</pre>
        <p>
          Add <code>--scope user</code> before the server name to make it available in every
          project, not just the one you're currently in:
        </p>
        <pre className="mcp-code-block">claude mcp add --transport http --scope user als-datasets {MCP_URL}</pre>
        <p>
          Check it connected with <code>claude mcp list</code> (or <code>/mcp</code> inside a
          session) -- look for a <code>Connected</code> status. Remove it later with{' '}
          <code>claude mcp remove als-datasets</code>.
        </p>
      </section>

      <section className="mcp-connect-section">
        <h3>Claude Science</h3>
        <p className="section-caveat">
          Steps below are based on where this setting lives as of this writing -- worth
          double-checking the exact menu wording in your own account, since it hasn't been
          independently verified the way the Claude.ai/Claude Code steps above were.
        </p>
        <ol>
          <li>Go to <strong>Customize &rarr; Connectors &rarr; Add connector</strong>.</li>
          <li>Choose <strong>Remote URL</strong>.</li>
          <li>Paste this URL: <code>{MCP_URL}</code> <CopyUrlButton /></li>
          <li>Give it a name, then click <strong>Add</strong>.</li>
        </ol>
      </section>
    </div>
  )
}
