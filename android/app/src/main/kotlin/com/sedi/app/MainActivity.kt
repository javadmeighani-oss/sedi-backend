package com.sedi.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/// Bounded Sedi Gadget BLE runtime permission seam (G9).
/// API 31+: BLUETOOTH_SCAN + BLUETOOTH_CONNECT.
/// API ≤30: ACCESS_FINE_LOCATION only.
class MainActivity : FlutterActivity() {
    private val channelName = "sedi/ble_permissions"
    private val requestCode = 9911
    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "requestBlePermissions" -> requestBlePermissions(result)
                    "openAppSettings" -> {
                        openAppSettings()
                        result.success(true)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    private fun neededPermissions(): Array<String> {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT,
            )
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    private fun requestBlePermissions(result: MethodChannel.Result) {
        if (pendingResult != null) {
            result.error("BUSY", "Permission request already in progress", null)
            return
        }
        val needed = neededPermissions()
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) {
            result.success("granted")
            return
        }
        pendingResult = result
        ActivityCompat.requestPermissions(this, missing.toTypedArray(), requestCode)
    }

    private fun openAppSettings() {
        val intent = Intent(
            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.fromParts("package", packageName, null),
        )
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != this.requestCode) return
        val result = pendingResult ?: return
        pendingResult = null

        if (grantResults.isNotEmpty() &&
            grantResults.all { it == PackageManager.PERMISSION_GRANTED }
        ) {
            result.success("granted")
            return
        }

        val permanentlyDenied = permissions.any { perm ->
            val denied = ContextCompat.checkSelfPermission(this, perm) !=
                PackageManager.PERMISSION_GRANTED
            denied && !ActivityCompat.shouldShowRequestPermissionRationale(this, perm)
        }
        result.success(if (permanentlyDenied) "permanentlyDenied" else "denied")
    }
}
