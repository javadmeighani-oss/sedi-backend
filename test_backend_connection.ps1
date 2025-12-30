# Test Backend Connection Script
# Tests all critical endpoints for frontend integration

$baseUrl = "http://91.107.168.130:8000"
$timeout = 10

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing Backend Connection" -ForegroundColor Cyan
Write-Host "Base URL: $baseUrl" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Root Endpoint
Write-Host "Test 1: Root Endpoint (/)..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/" -Method GET -TimeoutSec $timeout
    Write-Host "✅ Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "Response: $($response.Content.Substring(0, [Math]::Min(200, $response.Content.Length)))..." -ForegroundColor Gray
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 2: API Docs
Write-Host "Test 2: API Documentation (/docs)..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/docs" -Method GET -TimeoutSec $timeout
    Write-Host "✅ Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "✅ API Docs accessible" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 3: Chat Endpoint (POST) - Anonymous User
Write-Host "Test 3: Chat Endpoint (POST /interact/chat) - Anonymous User..." -ForegroundColor Yellow
try {
    $chatUrl = "$baseUrl/interact/chat?message=Hello&lang=en"
    $response = Invoke-WebRequest -Uri $chatUrl -Method POST -TimeoutSec $timeout
    Write-Host "✅ Status: $($response.StatusCode)" -ForegroundColor Green
    $jsonResponse = $response.Content | ConvertFrom-Json
    Write-Host "✅ Message received: $($jsonResponse.message.Substring(0, [Math]::Min(100, $jsonResponse.message.Length)))..." -ForegroundColor Green
    Write-Host "✅ User ID: $($jsonResponse.user_id)" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "Response Body: $responseBody" -ForegroundColor Red
    }
}
Write-Host ""

# Test 4: Chat Endpoint with Greeting Marker
Write-Host "Test 4: Chat Endpoint with Greeting Marker (__GREETING__)..." -ForegroundColor Yellow
try {
    $greetingUrl = "$baseUrl/interact/chat?message=__GREETING__&lang=en"
    $response = Invoke-WebRequest -Uri $greetingUrl -Method POST -TimeoutSec $timeout
    Write-Host "✅ Status: $($response.StatusCode)" -ForegroundColor Green
    $jsonResponse = $response.Content | ConvertFrom-Json
    Write-Host "✅ Greeting received: $($jsonResponse.message.Substring(0, [Math]::Min(100, $jsonResponse.message.Length)))..." -ForegroundColor Green
} catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 5: Health Check
Write-Host "Test 5: Health Check..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/health" -Method GET -TimeoutSec $timeout -ErrorAction SilentlyContinue
    if ($response) {
        Write-Host "✅ Status: $($response.StatusCode)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Health endpoint not found (this is OK)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Health endpoint not found (this is OK)" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

