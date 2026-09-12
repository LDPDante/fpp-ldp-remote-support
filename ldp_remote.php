<?php
// LDP Remote Support - status + on/off control page.
// Rendered inside the normal FPP UI (wrap=1). $pluginName / $settings are preset by FPP.
if (!isset($pluginName)) { $pluginName = "fpp-ldp-remote-support"; }

$TS  = "/usr/bin/tailscale";
$raw = @shell_exec("$TS status --json 2>/dev/null");
$st  = json_decode($raw, true);

$backend  = is_array($st) ? ($st['BackendState'] ?? 'Unknown') : 'Unknown';
$selfIP   = is_array($st) ? ($st['Self']['TailscaleIPs'][0] ?? '') : '';
$selfHost = is_array($st) ? ($st['Self']['HostName'] ?? '') : '';

if ($backend === 'Running' && $selfIP !== '') { $badge = 'success';   $label = 'Connected'; }
elseif ($backend === 'Stopped')               { $badge = 'secondary'; $label = 'Turned off'; }
elseif ($backend === 'NeedsLogin' || $backend === 'NoState') { $badge = 'warning'; $label = 'Not enrolled yet'; }
else { $badge = 'secondary'; $label = htmlspecialchars($backend); }
?>
<div class="row">
 <div class="col-md-12">
  <div class="card mt-2">
   <div class="card-header"><b>LDP Remote Support</b></div>
   <div class="card-body">

    <p class="mb-2">
      Status: <span class="badge bg-<?php echo $badge; ?>"><?php echo $label; ?></span>
      <?php if ($selfIP):   ?>&nbsp;&nbsp;Address: <code><?php echo htmlspecialchars($selfIP); ?></code><?php endif; ?>
      <?php if ($selfHost): ?>&nbsp;&nbsp;Name: <code><?php echo htmlspecialchars($selfHost); ?></code><?php endif; ?>
    </p>

    <div class="mt-2 mb-2 d-flex align-items-center flex-wrap gap-2">
      <?php PrintSettingCheckbox("Enable LDP Remote Support", "RemoteSupportEnabled", 0, 0, "True", "False", $pluginName, "", "True"); ?>
      <button type="button" class="btn btn-primary btn-sm" onclick="ldpApply(this)">Apply now</button>
      <button type="button" class="btn btn-outline-secondary btn-sm" onclick="location.reload()">Refresh</button>
    </div>

    <div class="alert alert-info mt-3 mb-0" role="alert">
      <b>What this is:</b> When enabled, this controller securely connects to the private
      <b>L Designs Plus support network</b> so L Designs Plus can help set it up and fix issues
      remotely. It does <u>not</u> expose anything else on your home network, and you can turn it
      off here at any time &mdash; uncheck the box and click <b>Apply now</b>.
    </div>

   </div>
  </div>
 </div>
</div>

<script>
function ldpApply(btn){
  btn.disabled = true; btn.innerText = 'Applying...';
  fetch('/api/command/LDP%20Remote%20Apply', {method:'POST'})
    .then(function(){ setTimeout(function(){ location.reload(); }, 3000); })
    .catch(function(){ setTimeout(function(){ location.reload(); }, 3000); });
}
</script>
