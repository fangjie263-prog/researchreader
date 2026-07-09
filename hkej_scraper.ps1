# hkej_news_scraper.ps1
param([int]$NumPages=5,[string]$OutputDir="")
if(-not $OutputDir){$OutputDir=Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "outputs"}
if(-not(Test-Path $OutputDir)){New-Item -ItemType Directory -Path $OutputDir|Out-Null}
$dateStr=Get-Date -Format "yyyy-MM-dd_HHmmss"
$outputFile=Join-Path $OutputDir "hkej_news_${dateStr}.txt"
Write-Host "=== 信报即时新闻抓取 ===" -ForegroundColor Cyan
Write-Host "抓取页数: $NumPages 页"
Write-Host "输出文件: $outputFile"
Write-Host ""
Write-Host "[1/3] 正在抓取首页..." -NoNewline
try{$homepage=Invoke-WebRequest -Uri "https://www.hkej.com/instantnews" -UseBasicParsing -TimeoutSec 30;Write-Host " 成功" -ForegroundColor Green}catch{Write-Host " 失败: $_" -ForegroundColor Red;exit 1}
$allLinks=@{}
$page1Links=[regex]::Matches($homepage.Content,'(?<=href=")(/instantnews/[a-z]+/article/\d+/[^"]*)(?=")')
foreach($l in $page1Links){$v=$l.Groups[1].Value;if(-not $allLinks.ContainsKey($v)){$allLinks[$v]=$true}}
Write-Host "[2/3] 第1页找到 $($page1Links.Count) 条" -ForegroundColor Green
for($p=2;$p-le $NumPages;$p++){
$pageUrl="https://www.hkej.com/instantnews/index?page=$p"
Write-Host "[2/3] 正在抓取第 $p 页..." -NoNewline
try{
$pageResp=Invoke-WebRequest -Uri $pageUrl -UseBasicParsing -TimeoutSec 30
$pageLinks=[regex]::Matches($pageResp.Content,'(?<=href=")(/instantnews/[a-z]+/article/\d+/[^"]*)(?=")')
$newCount=0
foreach($l in $pageLinks){$v=$l.Groups[1].Value;if(-not $allLinks.ContainsKey($v)){$allLinks[$v]=$true;$newCount++}}
Write-Host " 本页 $($pageLinks.Count) 条，新增 $newCount 条" -ForegroundColor Green
Start-Sleep -Milliseconds 500
}catch{
Write-Host " 失败" -ForegroundColor Red
}
}
Write-Host "[3/3] 共 $($allLinks.Count) 条独立新闻，开始逐条抓取正文..." -ForegroundColor Green
$linkArray=@($allLinks.Keys)
$results=@()
$successCount=0
$failCount=0
for($i=0;$i-lt $linkArray.Count;$i++){
$relUrl=$linkArray[$i]
$fullUrl="https://www.hkej.com"+$relUrl
$parsed=$relUrl -split '/'
$cat=$parsed[2]
$titleEncoded=$parsed[5]
$urlTitle=[System.Net.WebUtility]::UrlDecode($titleEncoded)
$titlePreview=$urlTitle.Substring(0,[Math]::Min(30,$urlTitle.Length))
Write-Host "[$($i+1)/$($linkArray.Count)] $titlePreview..." -NoNewline -ForegroundColor Gray
try{
$article=Invoke-WebRequest -Uri $fullUrl -UseBasicParsing -TimeoutSec 30
$articleBody=$article.Content
$idx=$articleBody.IndexOf("article-content")
if($idx -gt 0){
$rest=$articleBody.Substring($idx)
$endIdx=$rest.IndexOf("</div>")
if($endIdx -gt 0){
$inner=$rest.Substring(0,$endIdx+6)
$cleanText=[regex]::Replace($inner,'<[^>]+>','')
$cleanText=$cleanText -replace '\s+',' '
$cleanText=$cleanText.Trim()
}else{$cleanText="(未能提取正文)"}
}else{$cleanText="(未能提取正文)"}
$results+="="*50
$results+="标题: $urlTitle"
$results+="链接: $fullUrl"
$results+="分类: $cat"
$results+="正文:"
$results+=$cleanText
$results+=""
if($cleanText-eq"(未能提取正文)"){
$failCount++;Write-Host " [提取失败]" -ForegroundColor Yellow
}else{
$successCount++;Write-Host " [OK]" -ForegroundColor Green
}
}catch{
$results+="="*50
$results+="标题: $urlTitle"
$results+="链接: $fullUrl"
$results+="状态: 失败 - $($_.Exception.Message)"
$results+=""
$failCount++;Write-Host " [抓取失败]" -ForegroundColor Red
}
Start-Sleep -Milliseconds 400
}
$header="信报即时新闻抓取报告`n"
$header+="抓取时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n"
$header+="来源: https://www.hkej.com/instantnews`n"
$header+="抓取页数: 1-$NumPages 页`n"
$header+="共抓取: $($linkArray.Count) 条 | 成功: $successCount | 失败: $failCount`n`n"
$fullContent=$header+($results-join"`n")
[System.IO.File]::WriteAllText($outputFile,$fullContent,[System.Text.Encoding]::UTF8)
Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Cyan
Write-Host "成功: $successCount | 失败: $failCount" -ForegroundColor $(if($failCount-eq 0){"Green"}else{"Yellow"})
Write-Host "文件已保存至: $outputFile" -ForegroundColor Green