<?php
// LDP Port Map - which prop goes on which port, from the xLights show.
// The bench tool (tools/make_port_map.py --push) or the Upload button stores the
// map as JSON in FPP's config dir (survives plugin updates); portmap/portmap.js
// draws it. Writes need the same per-unit token as the Connect button, so another
// website can't overwrite the map. &nopage=1 = full-screen page for phones / QR.
if (!isset($pluginName)) { $pluginName = "fpp-ldp-remote-support"; }
$cfgDir  = (isset($settings['configDirectory']) && $settings['configDirectory'] !== '')
         ? $settings['configDirectory'] : '/home/fpp/media/config';
$mapFile = $cfgDir . '/ldp-portmap.json';
$maxSize = 2 * 1024 * 1024;
$full    = isset($_GET['nopage']);
$asJson  = (($_GET['format'] ?? '') === 'json');

$csrf = ReadSettingFromFile("CsrfToken", $pluginName);
if (!is_string($csrf) || strlen($csrf) < 32) {
    $csrf = bin2hex(random_bytes(16));
    WriteSettingToFile("CsrfToken", $csrf, $pluginName);
}

function ldp_pm_valid($d) {
    return is_array($d) && isset($d['controllers']) && is_array($d['controllers']);
}

// --- writes: POST + token only ---
$msg = ''; $err = '';
$action = $_POST['ldp_action'] ?? '';
if ($action !== '') {
    if (!hash_equals($csrf, (string)($_POST['ldp_token'] ?? ''))) {
        $err = 'Not allowed (bad or missing token). Reload the page and try again.';
    } elseif ($action === 'portmap_upload') {
        $raw = (string)($_POST['portmap'] ?? '');
        $data = (strlen($raw) <= $maxSize) ? json_decode($raw, true) : null;
        if (!ldp_pm_valid($data)) {
            $err = 'That file does not contain a port map (make it with tools/make_port_map.py).';
        } else {
            $tmp = $mapFile . '.tmp';
            if (@file_put_contents($tmp, json_encode($data)) !== false && @rename($tmp, $mapFile)) {
                $msg = 'Port map saved.';
            } else {
                @unlink($tmp);
                $err = 'Could not save the port map on this controller.';
            }
        }
    } elseif ($action === 'portmap_clear') {
        @unlink($mapFile);
        $msg = 'Port map removed.';
    }
    if ($asJson) {
        header('Content-Type: application/json');
        echo json_encode($err === '' ? array('ok' => true, 'message' => $msg) : array('ok' => false, 'error' => $err));
        exit;
    }
}

$map = null;
if (is_file($mapFile)) {
    $map = json_decode((string)@file_get_contents($mapFile), true);
    if (!ldp_pm_valid($map)) { $map = null; }
}
$css = (string)@file_get_contents(__DIR__ . '/portmap/portmap.css');
$js  = (string)@file_get_contents(__DIR__ . '/portmap/portmap.js');
$blob = json_encode($map, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT);
$base = "plugin.php?plugin=" . urlencode($pluginName) . "&page=portmap.php";
$h = function ($s) { return htmlspecialchars((string)$s, ENT_QUOTES); };

if ($full) { ?>
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><?= $h(($map['title'] ?? 'Port') . ' Port Map') ?></title>
<style><?= $css ?>
body{margin:0;padding:16px;background:var(--pm-bg)}
@media (prefers-color-scheme:dark){body{background:#111214}}
.pm-none{max-width:520px}</style></head>
<body class="ldp-pm pm-auto" data-ldp-token="<?= $h($csrf) ?>">
<?php } else { ?>
<style><?= $css ?>
#ldpPortMapWrap{max-width:1200px}
#ldpPortMapWrap .pm-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 12px}
#ldpPortMapWrap .pm-box{background:var(--pm-bg);border-radius:10px;padding:16px}
#ldpPortMapWrap .pm-ok{color:#1e7d32;font-weight:600}
#ldpPortMapWrap .pm-err{color:#b3261e;font-weight:600}</style>
<div id="ldpPortMapWrap" class="ldp-pm" data-ldp-token="<?= $h($csrf) ?>">
  <div class="pm-bar">
    <a class="buttons btn-outline-success" href="<?= $h($base . '&nopage=1') ?>" target="_blank">Open full screen (phone)</a>
    <label class="buttons btn-outline-light" style="cursor:pointer">Upload map&hellip;
      <input type="file" id="pmFile" accept=".html,.htm,.json" style="display:none"></label>
    <?php if ($map) { ?>
    <form method="post" action="<?= $h($base) ?>" style="display:inline" onsubmit="return confirm('Remove the port map from this controller?')">
      <input type="hidden" name="ldp_action" value="portmap_clear">
      <input type="hidden" name="ldp_token" value="<?= $h($csrf) ?>">
      <button class="buttons btn-outline-danger" type="submit">Remove</button></form>
    <?php } ?>
    <span id="pmMsg" class="<?= $err ? 'pm-err' : 'pm-ok' ?>"><?= $h($err ?: $msg) ?></span>
  </div>
  <form method="post" action="<?= $h($base) ?>" id="pmUpload" style="display:none">
    <input type="hidden" name="ldp_action" value="portmap_upload">
    <input type="hidden" name="ldp_token" value="<?= $h($csrf) ?>">
    <input type="hidden" name="portmap" id="pmData"></form>
  <div class="pm-box">
<?php } ?>
<div id="ldpPortMap"></div>
<?php if (!$map) { ?>
<div class="pm-none">
  <h1>Port Map</h1>
  <p class="pm-meta">No port map on this controller yet.</p>
  <p>On the LDP bench, from the xLights show folder:</p>
  <p><code>python tools/make_port_map.py &lt;show folder&gt; -c &lt;controller&gt; --push &lt;this controller's IP&gt;</code></p>
  <p>or make the map and use <b>Upload map</b> on this page in FPP (Status/Control &rarr; Port Map).</p>
</div>
<?php } ?>
<script><?= $js ?></script>
<script>
(function () {
  var data = <?= $blob ?>;
  if (data) LDPPortMap.render(data, document.getElementById('ldpPortMap'));
  var file = document.getElementById('pmFile');
  if (!file) return;
  file.addEventListener('change', function () {
    var f = file.files[0], msg = document.getElementById('pmMsg');
    if (!f) return;
    f.text().then(function (txt) {
      // accept the .json, or the standalone .html the bench tool writes
      var m = txt.match(/LDPPortMap\.render\(([\s\S]*?), document\.getElementById\('pm'\)\)/);
      var d;
      try { d = JSON.parse(m ? m[1] : txt); } catch (e) { d = null; }
      if (!LDPPortMap.valid(d)) {
        msg.className = 'pm-err';
        msg.textContent = 'That file is not a port map (make it with tools/make_port_map.py).';
        return;
      }
      document.getElementById('pmData').value = JSON.stringify(d);
      document.getElementById('pmUpload').submit();
    });
  });
})();
</script>
<?php if ($full) { ?>
</body></html>
<?php } else { ?>
  </div>
</div>
<?php } ?>
