#!/usr/bin/env node
/**
 * Minimal pure-TS unit test runner — no new deps.
 *
 * The app has no JS test runner (UI tests are Maestro). These tests cover the
 * *pure* personalization helpers (lib/toneCopy.ts, lib/personalization.ts) that
 * must stay deterministic and cold-start-safe. We transform the .ts on require
 * with @babel/core + babel-preset-expo (both already devDependencies) and run
 * every *.test.ts in mobile/__tests__ with node's built-in `assert`.
 *
 *   node scripts/run-unit-tests.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');
const Module = require('module');

// Register a .ts loader so `require('./x.ts')` / `require('./x')` transforms on the fly.
Module._extensions['.ts'] = function (module, filename) {
    const { code } = babel.transformFileSync(filename, {
        presets: ['babel-preset-expo'],
        filename,
        babelrc: false,
        configFile: false,
    });
    module._compile(code, filename);
};
// Let bare `require('./foo')` resolve to foo.ts.
if (!Module._extensions['.ts']) throw new Error('failed to register .ts loader');

const testsDir = path.join(__dirname, '..', '__tests__');
const files = fs
    .readdirSync(testsDir)
    .filter((f) => f.endsWith('.test.ts'))
    .sort();

let passed = 0;
let failed = 0;
const failures = [];

// AWAIT each test. A synchronous `fn()` would count an async test as passed the
// instant it returned its (still-pending) promise, so a REJECTED assertion would
// surface as an unhandled rejection while the suite reported green — vacuously
// passing tests are worse than no tests.
async function run() {
    for (const f of files) {
        const full = path.join(testsDir, f);
        try {
            const mod = require(full);
            const tests = mod.tests || {};
            for (const [name, fn] of Object.entries(tests)) {
                try {
                    await fn();
                    passed += 1;
                    console.log(`  ✓ ${f} — ${name}`);
                } catch (err) {
                    failed += 1;
                    failures.push(`${f} — ${name}: ${err && err.message}`);
                    console.log(`  ✗ ${f} — ${name}`);
                }
            }
        } catch (err) {
            failed += 1;
            failures.push(`${f} (load): ${err && err.stack ? err.stack : err}`);
            console.log(`  ✗ ${f} (failed to load)`);
        }
    }

    console.log(`\n${passed} passed, ${failed} failed`);
    if (failed > 0) {
        console.log('\nFailures:');
        for (const x of failures) console.log(`  - ${x}`);
        process.exit(1);
    }
}

// A rejected promise that escapes must FAIL the run, never pass silently.
process.on('unhandledRejection', (err) => {
    console.error('\nUnhandled rejection in test run:', err);
    process.exit(1);
});

run();
