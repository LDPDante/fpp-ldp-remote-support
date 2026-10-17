<?php
// LDP Port Map - live view. Reads the port setup straight from the controllers this
// FPP sends to (and this unit's own pixel ports), so a port change uploaded from
// xLights shows up with no extra step. Controllers only store the FIRST prop's name on
// a port, so the full chain is filled in from the models FPP holds (uploaded by
// xLights FPP Connect), matched by channel. Where the two disagree the port says so.
// Read-only: only GETs and Falcon "query" calls. Same data shape as make_port_map.py.

/** $get($url) -> body|false, $post($url, $json) -> body|false. $api = this FPP's API base. */
function ldp_pm_live($api, $get, $post, $title = '') {
    $models = ldp_pm_models($get($api . '/models'));
    $out = array(); $modelsFor = array();
    $uo = json_decode((string)$get($api . '/channel/output/universeOutputs'), true);
    $targets = array();
    foreach ((array)($uo['channelOutputs'] ?? array()) as $co) {
        foreach ((array)($co['universes'] ?? array()) as $u) {
            if (empty($u['active']) || empty($u['address']) || !filter_var($u['address'], FILTER_VALIDATE_IP)) continue;
            $ip = $u['address'];
            if (isset($targets[$ip])) continue;
            $targets[$ip] = array('ip' => $ip, 'name' => (string)($u['description'] ?? $ip), 'offset' => (int)($u['startChannel'] ?? 1));
        }
    }
    // this unit's own pixel ports (LDP Ready-to-Run boxes drive pixels from the Pi itself)
    $own = json_decode((string)$get($api . '/channel/output/co-pixelStrings'), true);
    if (is_array($own) && !empty($own['channelOutputs'])) {
        $c = ldp_pm_fpp_strings($own, 1, $models);
        if ($c['ports']) { $c['name'] = 'This controller'; $c['vendor'] = 'FPP'; $out[] = $c; }
    }
    foreach ($targets as $t) {
        $c = ldp_pm_read_controller($t, $get, $post, $models);
        $out[] = $c;
    }
    return array('version' => 1, 'live' => true, 'title' => $title !== '' ? $title : 'Port Map',
        'generated' => date('Y-m-d H:i'), 'modelsCount' => count($models), 'controllers' => $out, 'unassigned' => array());
}

function ldp_pm_models($raw) {
    $d = json_decode((string)$raw, true);
    if (isset($d['models'])) $d = $d['models'];
    $m = array();
    foreach ((array)$d as $x) {
        if (!is_array($x) || !isset($x['Name'], $x['StartChannel'], $x['ChannelCount'])) continue;
        $cpn = max(1, (int)($x['ChannelCountPerNode'] ?? 3));
        $s = (int)$x['StartChannel']; $n = (int)$x['ChannelCount'];
        if ($s < 1 || $n < 1) continue;
        $m[] = array('name' => (string)$x['Name'], 'start' => $s, 'end' => $s + $n - 1, 'cpn' => $cpn);
    }
    usort($m, function ($a, $b) { return $a['start'] - $b['start']; });
    return $m;
}

function ldp_pm_read_controller($t, $get, $post, $models) {
    $base = 'http://' . $t['ip'];
    $c = array('name' => $t['name'], 'vendor' => '', 'model' => '', 'ip' => $t['ip'], 'pixels' => 0, 'ports' => array(), 'dmx' => array());
    $st = $get($base . '/status.xml');
    if (is_string($st) && strpos($st, '<fv>') !== false) {              // Falcon V4/V5
        $c['vendor'] = 'Falcon';
        if (preg_match('#<n>([^<]*)</n>#', $st, $mt)) { $c['model'] = $mt[1]; if (stripos($mt[1], 'Falcon') === 0) $c['vendor'] = ''; }   // e.g. Falcon_F16V4_0D1C
        $rows = array();
        for ($b = 0; $b < 40; $b++) {                                       // paged: B = batch, F = 1 on the last one
            $r = json_decode((string)$post($base . '/api', json_encode(array('T' => 'Q', 'M' => 'SP', 'B' => $b, 'E' => 0, 'I' => 0, 'P' => new stdClass()))), true);
            if (!is_array($r) || !isset($r['P']['A'])) { if (!$rows) $c['error'] = "couldn't read the port settings"; break; }
            foreach ($r['P']['A'] as $a) $rows[] = $a;
            if (!empty($r['F'])) break;
        }
        $segs = array();
        foreach ($rows as $a) {
            $segs[] = array('port' => (int)$a['p'] + 1, 'remote' => (int)($a['r'] ?? 0) > 0 ? chr(64 + (int)$a['r']) : '',
                'idx' => (int)($a['s'] ?? 0), 'start' => (int)$a['sc'] + $t['offset'], 'px' => (int)$a['n'],
                'ns' => (int)($a['ns'] ?? 0), 'ne' => (int)($a['ne'] ?? 0), 'name' => (string)($a['nm'] ?? ''),
                'bright' => (int)($a['b'] ?? 100));
        }
        ldp_pm_fill($c, $segs, $models);
        return $c;
    }
    $ps = json_decode((string)$get($base . '/api/channel/output/co-pixelStrings'), true);   // FPP-based (Kulp, other Pis)
    if (is_array($ps) && !empty($ps['channelOutputs'])) {
        $f = ldp_pm_fpp_strings($ps, $t['offset'], $models);
        $f['name'] = $c['name']; $f['ip'] = $c['ip']; $f['vendor'] = 'FPP';
        return $f;
    }
    $c['error'] = "not reachable from this controller right now";
    return $c;
}

/** FPP pixel-string config (co-pixelStrings) -> ports. startChannel there is 0-based. */
function ldp_pm_fpp_strings($ps, $offset, $models) {
    $c = array('name' => '', 'vendor' => 'FPP', 'model' => '', 'ip' => '', 'pixels' => 0, 'ports' => array(), 'dmx' => array());
    $segs = array();
    foreach ((array)$ps['channelOutputs'] as $co) {
        if (isset($co['enabled']) && !$co['enabled']) continue;
        if (!empty($co['subType'])) $c['model'] = (string)$co['subType'];
        foreach ((array)($co['outputs'] ?? array()) as $o) {
            $port = (int)($o['portNumber'] ?? 0) + 1;
            foreach ((array)($o['virtualStrings'] ?? array()) as $i => $v) {
                $segs[] = array('port' => $port, 'remote' => '', 'idx' => $i, 'start' => (int)($v['startChannel'] ?? 0) + $offset,
                    'px' => (int)($v['pixelCount'] ?? 0), 'ns' => (int)($v['nullNodes'] ?? 0), 'ne' => (int)($v['endNulls'] ?? 0),
                    'name' => (string)($v['description'] ?? ''), 'bright' => (int)($v['brightness'] ?? 100));
            }
        }
    }
    ldp_pm_fill($c, $segs, $models);
    return $c;
}

/** Group segments by port, then name each one's props from the models in its channel range. */
function ldp_pm_fill(&$c, $segs, $models) {
    $byPort = array();
    foreach ($segs as $s) $byPort[$s['port'] . '|' . $s['remote']][] = $s;
    uksort($byPort, function ($a, $b) {
        $pa = explode('|', $a); $pb = explode('|', $b);
        return ((int)$pa[0] - (int)$pb[0]) ?: strcmp($pa[1], $pb[1]);
    });
    foreach ($byPort as $key => $list) {
        usort($list, function ($a, $b) { return $a['idx'] - $b['idx']; });
        list($port, $remote) = explode('|', $key);
        $props = array(); $warn = array(); $total = 0;
        foreach ($list as $s) {
            if ($s['px'] <= 0) continue;
            $total += $s['px'] + $s['ns'] + $s['ne'];
            $named = ldp_pm_name_range($s, $models);
            if ($named['warn']) $warn[] = $named['warn'];
            $p = $named['props'];
            if ($s['ns']) $p[0]['null'] += $s['ns'];
            if ($s['ne']) $p[count($p) - 1]['endnull'] += $s['ne'];
            if ($s['bright'] && $s['bright'] != 100) foreach ($p as &$q) { $q['notes'][] = $s['bright'] . '% bright'; } unset($q);
            $props = array_merge($props, $p);
        }
        $port = array('port' => (int)$port, 'remote' => $remote, 'props' => $props);
        if ($props) $port['total'] = $total;
        if ($warn) $port['warn'] = implode(' ', array_unique($warn));
        $c['ports'][] = $port;
        $c['pixels'] += $total;
    }
}

function ldp_pm_same($a, $b) {          // FPP stores xLights names with spaces as underscores
    $n = function ($s) { return strtolower(str_replace(array(' ', '_'), '', $s)); };
    return $n($a) === $n($b);
}

/** One controller string -> the props in it, by channel. Falls back to the controller's own name. */
function ldp_pm_name_range($s, $models) {
    // 1) anchored: the controller stores the first prop's name; start at that model and follow the
    //    chain (models are laid out back to back), so a channel shift elsewhere doesn't matter
    $at = -1;
    if ($s['name'] !== '') foreach ($models as $i => $m) if (ldp_pm_same($s['name'], $m['name'])) { $at = $i; break; }
    if ($at >= 0) {
        $props = array(); $left = $s['px']; $prevEnd = null;
        for ($i = $at; $i < count($models) && $left > 0; $i++) {
            $m = $models[$i];
            if ($prevEnd !== null && $m['start'] !== $prevEnd + 1) break;      // not the next prop in the chain
            $px = intdiv($m['end'] - $m['start'] + 1, $m['cpn']);
            $props[] = array('name' => $i === $at ? $s['name'] : $m['name'], 'pixels' => min($px, $left), 'null' => 0, 'endnull' => 0, 'notes' => array());
            $left -= $px; $prevEnd = $m['end'];
        }
        if ($left === 0) return array('props' => $props, 'warn' => '');
        if ($left > 0) $props[] = array('name' => '(unknown: ' . $left . ' px)', 'pixels' => $left, 'null' => 0, 'endnull' => 0, 'notes' => array());
        return array('props' => $props, 'warn' => 'The controller has ' . $s['px'] . ' px here, starting with "' . $s['name']
            . '", but the models on this FPP add up differently; upload models from xLights (FPP Connect) to refresh the names.');
    }
    // 2) by channel: the controller's string sits at FPP channel start..end
    $start = $s['start']; $end = $start + $s['px'] * 3 - 1;
    $hit = array();
    foreach ($models as $m) {
        if ($m['end'] < $start) continue;
        if ($m['start'] > $end) break;
        $hit[] = $m;
    }
    $only = array(array('name' => $s['name'] !== '' ? $s['name'] : 'Unnamed', 'pixels' => $s['px'], 'null' => 0, 'endnull' => 0, 'notes' => array()));
    if (!$hit) {
        return array('props' => $only, 'warn' => $s['name'] !== ''
            ? 'Only the first prop\'s name is stored on the controller; upload models from xLights (FPP Connect) to see the whole chain.' : '');
    }
    $props = array(); $ch = $start; $gap = false;
    foreach ($hit as $m) {
        $a = max($m['start'], $start); $b = min($m['end'], $end);
        if ($a !== $ch) $gap = true;
        $ch = $b + 1;
        $name = ($m['start'] < $start ? $m['name'] . ' (continued)' : $m['name']);
        if (!$props && $s['name'] !== '' && ldp_pm_same($s['name'], $m['name'])) $name = $s['name'];
        $props[] = array('name' => $name, 'pixels' => intdiv($b - $a + 1, $m['cpn']), 'null' => 0, 'endnull' => 0, 'notes' => array());
    }
    if ($ch !== $end + 1) $gap = true;
    $firstOk = $s['name'] === '' || preg_match('/^(Port|String) \d+$/', $s['name']) || ldp_pm_same($s['name'], $hit[0]['name']) || $hit[0]['start'] < $start;
    if ($gap || !$firstOk) {
        return array('props' => $props, 'warn' => 'The controller has ' . $s['px'] . ' px here' . ($s['name'] !== '' ? ', starting with "' . $s['name'] . '"' : '')
            . '. The names below come from the models on this FPP, which look older than the controller\'s setup; upload models from xLights (FPP Connect) to refresh them.');
    }
    return array('props' => $props, 'warn' => '');
}
