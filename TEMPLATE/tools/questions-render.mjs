// questions-render.mjs — the Open Questions page renderer (#547).
//
// VERSIONED SOURCE. tools/questions copies this file into the build directory
// (write-if-different) before invoking it, because ESM resolves a bare import
// from the IMPORTING FILE's own location and the node_modules that carries
// @json-render lives there. Do not edit the copy under questions/build/: the
// next render overwrites it.
//
// stdin: a json-render SPEC. stdout: an HTML FRAGMENT. Exit 3 = the spec was not
// JSON, exit 5 = the spec FAILED the catalog (unregistered type or bad prop),
// exit 4 = the render threw. The caller turns any non-zero exit into a NON-ZERO
// publish that writes nothing, so a fault here fails the command and the last
// good page keeps serving (owner order 2026-09-24: there is exactly ONE builder,
// so the artifact can state its own provenance).
//
// No JSX and no build step: React.createElement only, so a plain .mjs runs as
// written. The output carries NO <script> — the page stays a static artifact,
// which is why the vpn deploy is unchanged (agents renders, vpn rsyncs, Caddy
// serves).
//
// The catalog is a GUARDRAIL, not a formality: a spec can only name a component
// registered here, and validate() runs BEFORE the render, so an unknown type is
// REJECTED with the schema's own message instead of rendering nothing. That is
// why the page's CONTENT is typed too: a description is a sequence of block
// elements, not an HTML string injected as a prop. This file performs no raw
// HTML injection at all — React escapes every text node, so the
// escape-then-inject round trip is gone.
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import { z } from 'zod';
import { defineCatalog } from '@json-render/core';
import { schema } from '@json-render/react/schema';
import { defineRegistry, Renderer, JSONUIProvider } from '@json-render/react';

const h = React.createElement;

// A run of inline text. The Python side emits these from its bounded inline
// converter, so emphasis is typed data and never an HTML fragment.
const span = z.object({
  kind: z.enum(['Text', 'Strong', 'Emphasis', 'InlineCode']),
  text: z.string(),
});
const spans = z.array(span);

const catalog = defineCatalog(schema, {
  components: {
    Page: { props: z.object({ title: z.string(), expires_at: z.string() }), description: 'Page root' },
    QuestionSet: { props: z.object({ set_id: z.string(), lane: z.string(), anchor: z.string(), open: z.number().int() }), description: 'One lane block' },
    Question: { props: z.object({
      qid: z.string(), title: z.string(), recommendation: z.string().nullable(),
      token: z.string(), set: z.string(), action: z.string(), footer: z.string(),
      // multi (owner order 2026-09-28): how many options an answer may carry.
      // Optional, and an ABSENT value means single -- the store's pre-existing
      // questions carry no kind and must keep rendering radios.
      multi: z.boolean().optional(),
      // status + clarifyText (owner report 2026-09-25): a question in the
      // CLARIFYING state rendered identically to an open one, so the owner
      // tapped Clarify, reloaded, and saw no change at all -- the state
      // transition was invisible. clarifyText is the reader's own request.
      status: z.string().optional(), clarifyText: z.string().nullable().optional(),
    }), description: 'One question and its form' },
    // --- content blocks: the description is typed DATA, not an HTML fragment ---
    Heading: { props: z.object({ level: z.number().int().min(1).max(3), text: z.string() }), description: 'A section heading' },
    Paragraph: { props: z.object({ spans }), description: 'A paragraph of inline spans' },
    Table: { props: z.object({ headers: z.array(spans), rows: z.array(z.array(spans)) }), description: 'A table' },
    Mermaid: { props: z.object({ code: z.string() }), description: 'A mermaid diagram; this component owns the URL' },
    CodeBlock: { props: z.object({ lang: z.string(), code: z.string() }), description: 'A fenced code block' },
    List: { props: z.object({ items: z.array(spans), ordered: z.boolean() }), description: 'A bullet or numbered list' },
    // --- form controls ---
    Option: { props: z.object({ label: z.string(), value: z.string(), recommended: z.boolean().nullable(), multi: z.boolean().optional() }), description: 'A radio or checkbox option' },
    FreeText: { props: z.object({ label: z.string() }), description: 'Free-text answer' },
    Submit: { props: z.object({ label: z.string(), value: z.string() }), description: 'Submit button' },
    Clarify: { props: z.object({ label: z.string() }), description: 'Clarify button' },
  },
  actions: {},
});

// Python's base64.urlsafe_b64encode, reproduced exactly: mermaid.ink receives the
// SAME URL for the same diagram as the pre-port page did, padding included.
const b64url = (text) =>
  Buffer.from(text, 'utf8').toString('base64').replace(/\+/g, '-').replace(/\//g, '_');

const renderSpans = (list) => (list || []).map((s, i) => {
  if (s.kind === 'Strong') return h('strong', { key: i }, s.text);
  if (s.kind === 'Emphasis') return h('em', { key: i }, s.text);
  if (s.kind === 'InlineCode') return h('code', { key: i }, s.text);
  return h('span', { key: i }, s.text);
});

const { registry } = defineRegistry(catalog, {
  components: {
    // The TTL line is NOT rendered here: page_wrapper() emits it in the shell,
    // above <main>, alongside the noindex and charset chrome. Rendering it here
    // too printed the same expiry twice (owner report 2026-09-24). The spec
    // still CARRIES expires_at -- the spec is the page's description and stays
    // self-describing -- but the shell owns the one visible line.
    Page: ({ props, children }) => h('main', null,
      h('h1', null, props.title),
      children),
    // The LANE section (owner order 2026-09-25): a STABLE anchor so the owner
    // can be handed a URL pointing at one lane's questions. The anchor arrives
    // in the spec, so the page and the CLI cannot disagree about it.
    // A lane with nothing OPEN renders no section at all (owner order
    // 2026-09-28), superseding the earlier rule that an all-answered lane kept
    // its section so a handed-out anchor stayed live. The page ADDRESS is what
    // is permanent; a lane SECTION exists while that lane has an open question.
    QuestionSet: ({ props, children }) => h('section',
      { id: props.anchor, className: 'set', 'data-set': props.set_id },
      // Owner order 2026-09-28 (14:32): the factory name sits HERE, in the
      // section heading, not beside each question's own title. The card already
      // carries its context on a bottom line ("asked .. / lane .. / set qid"),
      // so a per-card chip said the same thing twice and crowded the heading the
      // reader actually scans. Section level is also where the name is USEFUL on
      // the aggregate, which mixes every factory. The names come from the
      // section's own card-derived set list, so a lane spanning two factories
      // names both. Subtle by idiom -- mono, dim, uppercase, small.
      h('h2', null,
        h('span', { className: 'qset' },
          props.set_id.split(',').join(' + ')), ' / ',
        props.lane + ' — ' + props.open + ' open'),
      children),
    // The form carries token, set and qid as hidden inputs: the answer backend
    // reads all three, and dropping any of them silently stops the page
    // submitting -- the one regression that would break the live endpoint. The
    // description blocks are children of the form, which is where the pre-port
    // page carried them.
    Question: ({ props, children }) => {
      // Owner order 2026-09-27: a CLARIFYING question is waiting on the LANE
      // (it must be amended back to open), not on the reader -- so it must not
      // occupy the space of an actionable question. The card shrinks and its
      // form collapses behind a native <details>: no JS, keyboard-accessible,
      // and opening the summary restores the FULL form, so the question stays
      // answerable. Inert with JS off, because <details> is native HTML.
      const clarifying = props.status === 'clarifying';
      const form = h('form', { method: 'post', action: props.action,
                  'hx-post': props.action,
                  'hx-target': "[id='" + props.set + '-' + props.qid + "']",
                  'hx-swap': 'outerHTML' },
        h('input', { type: 'hidden', name: 'token', value: props.token }),
        h('input', { type: 'hidden', name: 'set', value: props.set }),
        h('input', { type: 'hidden', name: 'qid', value: props.qid }),
        children);
      return h('section', { id: props.set + '-' + props.qid,
                            className: 'q' + (clarifying ? ' clarifying' : '') },
      // Owner order 2026-09-28 (15:5x): the card's OWN CONTEXT LINE opens the
      // card. It already states the age, the lane and the set+qid ("asked 2.9d
      // ago / lane HQ / meta-factory q3"), so it is the context a reader needs
      // BEFORE the title -- not a chip beside the title, and not a footnote
      // under the form. Moved from the bottom on the owner's order; the class
      // name is unchanged, so the page's existing styling idiom still applies.
      h('p', { className: 'age' }, props.footer,
        // Owner order 2026-09-30: the clarifying state rides HERE, on the
        // card's own context line, instead of in a band below the title. The
        // band said the same thing twice and took the space of an actionable
        // question; a chip states it in the place the reader already looks.
        clarifying
          ? h('span', { className: 'chip clarifying',
                        // The reader's own request rides as the chip's native
                        // tooltip. The band that used to print it is gone, and
                        // the words they typed on this page must stay reachable
                        // from it -- no layout, no new element, no second band.
                        title: props.clarifyText
                          ? 'you requested: ' + props.clarifyText
                          : 'you requested clarification' }, 'clarifying')
          : null),
      // Owner order 2026-09-28: the factory name is NOT repeated here. It
      // moved up into the section heading (see QuestionSet) -- the card already
      // states its own context on the bottom line below, so a chip before the
      // title said it twice. The heading is the question's title and nothing
      // else.
      h('h3', { className: 'qt' }, props.title),
      // The recommendation block is the page's SIGNATURE: an amber-ruled block
      // carrying the lane's own counsel, one line of type under a generated
      // label. Owner orders 2026-09-27 and 2026-09-30 pulled in opposite
      // directions here -- the first folded it behind a <summary>, the second
      // unfolded it again -- so what binds now is the 2026-09-30 order: the
      // counsel is short and it is the reason the card is worth reading, so it
      // renders directly and the label comes back as generated content.
      props.recommendation
        ? h('p', { className: 'rec' }, props.recommendation)
        : null,
      // Owner order 2026-09-30: the clarifying BAND is gone -- the chip on
      // the context line above states the state. The reader's own clarify text
      // still reaches the lane through the notify body, which is where the lane
      // acts on it; the page does not repeat it.
      // hx-*: the form swaps THIS question's own block in place instead of
      // navigating away (owner question 2026-09-24). The section id below is
      // the swap target. Inert without the vendored htmx, in which case the
      // form submits as a normal POST -- so the no-JS path is unaffected.
      //
      // The target is an ATTRIBUTE selector, not '#id'. A CSS selector may not
      // start with a digit, so a set id like `19f2d7` made '#19f2d7-q1'
      // invalid and htmx threw on querySelectorAll -- reported live by the
      // owner 2026-09-25. An attribute selector is valid for ANY id, so no
      // future factory key can break the swap.
      clarifying
        ? h('details', { className: 'clarifybox' },
            h('summary', null, 'Answer anyway'), form)
        : form);
    },
    Heading: ({ props }) => h('h' + Math.min(props.level + 1, 6), null, props.text),
    Paragraph: ({ props }) => h('p', null, renderSpans(props.spans)),
    Table: ({ props }) => {
      const head = h('tr', null,
        props.headers.map((cell, i) => h('th', { key: i }, renderSpans(cell))));
      const body = props.rows.map((row, i) => h('tr', { key: i },
        row.map((cell, j) => h('td', { key: j }, renderSpans(cell)))));
      return h('div', { className: 'tblwrap' },
        h('table', null, h('thead', null, head), h('tbody', null, body)));
    },
    Mermaid: ({ props }) => h('figure', null,
      h('img', { alt: 'diagram', src: 'https://mermaid.ink/img/' + b64url(props.code) })),
    CodeBlock: ({ props }) => h('pre', { 'data-lang': props.lang }, h('code', null, props.code)),
    List: ({ props }) => h(props.ordered ? 'ol' : 'ul', null,
      props.items.map((item, i) => h('li', { key: i }, renderSpans(item)))),
    // `chip`, not `rec`: the recommendation BAND and this badge are different
    // elements, and giving them one class name is the specificity trap where a
    // rule for one silently restyles the other.
    // A MULTI option is a checkbox and a single one a radio. They share the
    // name `choice` deliberately: the backend collects every value under that
    // name as a list, which is how several choices reach the CLI in one post.
    Option: ({ props }) => h('label', { className: 'opt' },
      h('input', { type: props.multi ? 'checkbox' : 'radio', name: 'choice',
                   value: props.value, defaultChecked: !!props.recommended }),
      h('span', null, props.label,
        props.recommended ? h('span', { className: 'chip' }, 'recommended') : null)),
    FreeText: ({ props }) => h('textarea', { name: 'text', rows: 2, placeholder: props.label }),
    Submit: ({ props }) => h('button', { type: 'submit', name: 'choice', value: props.value, className: 'primary' }, props.label),
    Clarify: ({ props }) => h('button', { type: 'submit', name: 'choice', value: 'clarify', className: 'ghost' }, props.label),
  },
});

let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { raw += chunk; });
process.stdin.on('end', () => {
  let spec;
  try {
    spec = JSON.parse(raw);
  } catch (err) {
    process.stderr.write('spec is not JSON: ' + err.message + '\n');
    process.exit(3);
  }
  // The guardrail runs BEFORE the render: an unregistered type or a bad prop is
  // REJECTED with the schema's own message, never rendered as nothing.
  const verdict = catalog.validate(spec);
  if (verdict && verdict.success === false) {
    const detail = verdict.error && verdict.error.message
      ? verdict.error.message.replace(/\s+/g, ' ').slice(0, 400)
      : 'spec rejected by the catalog';
    process.stderr.write('spec rejected by the catalog: ' + detail + '\n');
    process.exit(5);
  }
  try {
    const html = renderToStaticMarkup(
      h(JSONUIProvider, { registry, initialState: {} },
        h(Renderer, { spec, registry })));
    process.stdout.write(html);
  } catch (err) {
    process.stderr.write('render failed: ' + (err && err.message) + '\n');
    process.exit(4);
  }
});
