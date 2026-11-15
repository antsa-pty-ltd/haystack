#!/usr/bin/env node
'use strict';

// Decides which regions a workflow run releases to, from .github/regions.json.
//   push to master      -> every region with releaseOnMaster
//   workflow_dispatch   -> exactly the region chosen by the dispatcher; only
//                          from master unless the region sets masterOnly:false
//   anything else       -> no release (checks only)
// Prints GitHub Actions outputs: release=true|false and matrix=<JSON array>.

const fs = require('node:fs');
const path = require('node:path');

const planRelease = ({ regions, eventName, ref, requestedRegion }) => {
  const all = Object.values(regions);
  for (const region of all) {
    if (!/^[a-z]{2}$/.test(region.code || '') || regions[region.code] !== region) {
      throw new Error('Every region must be keyed by its own two-letter code');
    }
  }
  if (eventName === 'workflow_dispatch') {
    const region = regions[requestedRegion];
    if (!region) throw new Error(`Unknown region requested: ${requestedRegion || '(none)'}`);
    // Belt and braces with the environment's own branch policy: a region
    // marked masterOnly can never be released from an unreviewed ref.
    if (region.masterOnly !== false && ref !== 'refs/heads/master') {
      throw new Error(`${region.code} can only be released from master, not ${ref || '(no ref)'}`);
    }
    return [region];
  }
  if (eventName === 'push' && ref === 'refs/heads/master') {
    return all.filter((region) => region.releaseOnMaster === true);
  }
  return [];
};

if (require.main === module) {
  const regions = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), '.github/regions.json'), 'utf8'));
  const matrix = planRelease({
    regions,
    eventName: process.env.GITHUB_EVENT_NAME,
    ref: process.env.GITHUB_REF,
    requestedRegion: process.env.REQUESTED_REGION,
  });
  const lines = [`release=${matrix.length > 0}`, `matrix=${JSON.stringify(matrix)}`];
  if (process.env.GITHUB_OUTPUT) fs.appendFileSync(process.env.GITHUB_OUTPUT, `${lines.join('\n')}\n`);
  console.log(`Release plan: ${matrix.map((region) => region.code).join(', ') || 'checks only'}`);
}

module.exports = { planRelease };
