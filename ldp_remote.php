<?php
// LDP Remote Support - customer-facing connect/disconnect page.
// Rendered inside the FPP UI (wrap=1). $pluginName / FPP settings helpers are preset.
if (!isset($pluginName)) { $pluginName = "fpp-ldp-remote-support"; }
$TS  = "/usr/bin/tailscale";
$PLUGIN_DIR = "/home/fpp/media/plugins/fpp-ldp-remote-support";

// --- CSRF token: a per-unit secret stored in the plugin settings. Another website
//     can't read this page, so it can't forge a Connect/Disconnect request. ---
$csrf = ReadSettingFromFile("CsrfToken", $pluginName);
if (!is_string($csrf) || strlen($csrf) < 32) {
    $csrf = bin2hex(random_bytes(16));
    WriteSettingToFile("CsrfToken", $csrf, $pluginName);
}

// --- Actions change state only via POST + token. A bare ?enable=1 / ?disable=1
//     link (e.g. the QR card) just shows the matching confirm button. ---
$did = '';
$action = $_POST['ldp_action'] ?? '';
if ($action !== '' && hash_equals($csrf, (string)($_POST['ldp_token'] ?? ''))) {
    if ($action === 'enable') {
        WriteSettingToFile("RemoteSupportEnabled", "True", $pluginName);
        @shell_exec("nohup $PLUGIN_DIR/commands/apply.sh > /dev/null 2>&1 &");
        $did = 'enable';
    } elseif ($action === 'disable') {
        WriteSettingToFile("RemoteSupportEnabled", "False", $pluginName);
        @shell_exec("nohup $PLUGIN_DIR/commands/apply.sh > /dev/null 2>&1 &");
        $did = 'disable';
    }
}
$askDisable = ($did === '' && isset($_GET['disable']));

$raw = @shell_exec("$TS status --json 2>/dev/null");
$st  = json_decode($raw, true);
$backend   = is_array($st) ? ($st['BackendState'] ?? 'Unknown') : 'Unknown';
$selfIP    = is_array($st) ? ($st['Self']['TailscaleIPs'][0] ?? '') : '';
$connected = ($backend === 'Running' && $selfIP !== '');

// this page's URL without the action params (for the auto-refresh / links)
$base = "plugin.php?plugin=" . urlencode($pluginName) . "&page=ldp_remote.php";

// a one-button POST form carrying the CSRF token
function ldp_button($base, $csrf, $action, $label, $cls) {
    printf('<form method="post" action="%s" class="d-inline m-0">'
         . '<input type="hidden" name="ldp_action" value="%s">'
         . '<input type="hidden" name="ldp_token" value="%s">'
         . '<button type="submit" class="%s">%s</button></form>',
        htmlspecialchars($base), htmlspecialchars($action), htmlspecialchars($csrf),
        htmlspecialchars($cls), $label);
}
?>
<div class="row"><div class="col-md-12">
 <div class="card mt-2">
  <div class="card-header"><b>LDP Remote Support</b></div>
  <div class="card-body">

  <?php if ($did === 'enable' && !$connected): ?>
    <div class="alert alert-info">Connecting to L&nbsp;Designs&nbsp;Plus support&hellip; this takes a few seconds.</div>
    <script>setTimeout(function(){ location.href='<?php echo $base; ?>'; }, 8000);</script>
  <?php endif; ?>

  <?php if ($connected): ?>
    <div class="alert alert-success d-flex align-items-center justify-content-between flex-wrap gap-2">
      <span><b>&#10003; Connected to L&nbsp;Designs&nbsp;Plus support.</b> We can now help you remotely.</span>
      <?php ldp_button($base, $csrf, 'disable', 'Disconnect', $askDisable ? 'btn btn-danger btn-sm' : 'btn btn-outline-secondary btn-sm'); ?>
    </div>
    <?php if ($askDisable): ?>
      <p class="mb-2">Press <b>Disconnect</b> to turn off remote support.</p>
    <?php endif; ?>
    <p class="text-muted mb-0 small">Support address: <code><?php echo htmlspecialchars($selfIP); ?></code></p>
  <?php elseif ($did !== 'enable'): ?>
    <p class="mb-3">Connect this controller to L&nbsp;Designs&nbsp;Plus so we can help set it up and fix issues remotely. It&rsquo;s optional, and you can disconnect anytime.</p>
    <?php ldp_button($base, $csrf, 'enable', 'Connect to LDP Support', 'btn btn-primary btn-lg'); ?>
  <?php endif; ?>

  <div class="alert alert-light border mt-3 mb-0 small">
    When connected, this controller reaches L&nbsp;Designs&nbsp;Plus over a private, encrypted link. It does <u>not</u> expose anything else on your home network, and it stays off until you press <b>Connect</b>.
  </div>

  </div>
 </div>
</div></div>
