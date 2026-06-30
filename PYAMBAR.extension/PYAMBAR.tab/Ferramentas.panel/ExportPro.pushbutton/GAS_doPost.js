// ExportPro — Google Apps Script doPost
// Deploy como web app standalone em script.google.com
// Execute as: Me | Who has access: Anyone within Ambar Technologies
// Versao 2.2 — modo append: insere abaixo do conteudo existente em aba nomeada

function _uniqueTabName(ss, baseName) {
  if (!ss.getSheetByName(baseName)) return baseName;
  var n = 2;
  while (ss.getSheetByName(baseName + '-' + n)) n++;
  return baseName + '-' + n;
}

function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);
    var spreadsheetId = payload.spreadsheetId;
    if (!spreadsheetId) {
      throw new Error('spreadsheetId ausente no payload.');
    }
    var ss = SpreadsheetApp.openById(spreadsheetId);
    var mode = payload.mode || 'separate';
    var schedules = payload.schedules || [];

    if (mode === 'stacked') {
      // Todos os schedules empilhados em uma unica aba
      var tabName = payload.projectName || 'Dados';
      tabName = tabName.substring(0, 90).replace(/[\[\]:*?\/\\]/g, '_');
      tabName = _uniqueTabName(ss, tabName);
      var sheet = ss.insertSheet(tabName);
      var allRows = [];
      for (var i = 0; i < schedules.length; i++) {
        if (i > 0) allRows.push(['']);  // linha em branco entre schedules
        var s = schedules[i];
        var incHeader = s.includeHeader !== false;
        if (incHeader && s.headers && s.headers.length > 0) {
          allRows.push(s.headers);
        }
        for (var r = 0; r < s.rows.length; r++) {
          allRows.push(s.rows[r]);
        }
      }
      if (allRows.length > 0) {
        var maxCols = allRows.reduce(function(m, row) { return Math.max(m, row.length); }, 0);
        var padded = allRows.map(function(row) {
          var copy = row.slice();
          while (copy.length < maxCols) copy.push('');
          return copy;
        });
        sheet.getRange(1, 1, padded.length, maxCols).setValues(padded);
      }
      return ContentService.createTextOutput(
        JSON.stringify({ status: 'ok', mode: 'stacked', rows: allRows.length })
      ).setMimeType(ContentService.MimeType.JSON);
    }

    // mode === 'append': insert below existing content in a named tab
    if (mode === 'append') {
      var appendTabName = payload.tabName;
      if (!appendTabName) throw new Error('tabName missing for mode=append.');
      var appendSheet = ss.getSheetByName(appendTabName);
      if (!appendSheet) throw new Error('Tab "' + appendTabName + '" not found in spreadsheet.');
      var appendRows = [];
      for (var ai = 0; ai < schedules.length; ai++) {
        if (ai > 0) appendRows.push(['']);
        var as = schedules[ai];
        var aIncHeader = as.includeHeader !== false;
        if (aIncHeader && as.headers && as.headers.length > 0) {
          appendRows.push(as.headers);
        }
        for (var ar = 0; ar < as.rows.length; ar++) {
          appendRows.push(as.rows[ar]);
        }
      }
      if (appendRows.length > 0) {
        var maxCols = appendRows.reduce(function(m, row) { return Math.max(m, row.length); }, 0);
        if (appendSheet.getMaxColumns() < maxCols) {
          appendSheet.insertColumnsAfter(appendSheet.getMaxColumns(), maxCols - appendSheet.getMaxColumns());
        }

        // Encontra o ultimo row com dado SOMENTE nas colunas que serao preenchidas (A:maxCols).
        // Ignora formulas/dados em outras colunas para nao inflar a posicao de insercao.
        var totalRows = appendSheet.getLastRow();
        var startRow = 1;
        if (totalRows > 0) {
          var colValues = appendSheet.getRange(1, 1, totalRows, maxCols).getValues();
          for (var ri = colValues.length - 1; ri >= 0; ri--) {
            var hasData = false;
            for (var ci = 0; ci < colValues[ri].length; ci++) {
              if (colValues[ri][ci] !== '' && colValues[ri][ci] !== null) {
                hasData = true;
                break;
              }
            }
            if (hasData) {
              startRow = ri + 2; // ri e 0-based; +1 para 1-based, +1 para proxima linha
              break;
            }
          }
        }

        var padded = appendRows.map(function(row) {
          var copy = row.slice();
          while (copy.length < maxCols) copy.push('');
          return copy;
        });
        appendSheet.getRange(startRow, 1, padded.length, maxCols).setValues(padded);
      }
      return ContentService.createTextOutput(
        JSON.stringify({ status: 'ok', mode: 'append', tabName: appendTabName, rows: appendRows.length })
      ).setMimeType(ContentService.MimeType.JSON);
    }

    // mode === 'separate': uma aba por schedule
    var sheetsWritten = 0;
    for (var i = 0; i < schedules.length; i++) {
      var s = schedules[i];
      var tabName = (s.name || ('Sheet' + (i + 1))).substring(0, 90);
      tabName = tabName.replace(/[\[\]:*?\/\\]/g, '_');
      tabName = _uniqueTabName(ss, tabName);
      var sheet = ss.insertSheet(tabName);
      var rows = [];
      var incHeader = s.includeHeader !== false;
      if (incHeader && s.headers && s.headers.length > 0) {
        rows.push(s.headers);
      }
      for (var r = 0; r < s.rows.length; r++) {
        rows.push(s.rows[r]);
      }
      if (rows.length > 0) {
        var maxCols = rows.reduce(function(m, row) { return Math.max(m, row.length); }, 0);
        var padded = rows.map(function(row) {
          var copy = row.slice();
          while (copy.length < maxCols) copy.push('');
          return copy;
        });
        sheet.getRange(1, 1, padded.length, maxCols).setValues(padded);
      }
      sheetsWritten++;
    }
    return ContentService.createTextOutput(
      JSON.stringify({ status: 'ok', sheets: sheetsWritten })
    ).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ status: 'error', message: err.toString() })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}
