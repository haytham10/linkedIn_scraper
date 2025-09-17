/**
 * LinkedIn Lead Refinement - Google Apps Script

// ================================
// CONFIGURATION
// ================================

/**
 * Retrieve the Gemini API key from Script Properties
 * Set this in: Project Settings (gear icon) > Script Properties
 */
const GEMINI_API_KEY = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

/**
 * Configuration constants
 */
const CONFIG = {
  // Gemini API settings
  GEMINI_MODEL: 'gemini-2.5-flash',
  GEMINI_API_URL: 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
  
  // Execution limits
  MAX_EXECUTION_TIME: 4.5 * 60 * 1000, // 4.5 minutes in milliseconds
  
  // Status values
  STATUS: {
    SCRAPED: 'SCRAPED',
    COMPLETE: 'COMPLETE',
    FAILED_API_ERROR: 'FAILED - API Error',
    FAILED_NO_OUTPUT: 'FAILED - No AI Output',
    FAILED_INVALID_JSON: 'FAILED - Invalid AI JSON',
    FAILED_SCRIPT_ERROR: 'FAILED - Script Error',
    IN_PROGRESS: 'IN_PROGRESS'
  },
  
  // Project types for lead classification
  PROJECT_TYPES: [
    'Automated Reporting',
    'CRM Data Sync', 
    'Lead Nurturing',
    'Client Onboarding',
    'Internal Process Automation'
  ]
};

// ================================
// UTILITY FUNCTIONS
// ================================

/**
 * Clean and parse AI response that may contain JSON wrapped in markdown or other text
 * @param {string} responseText - Raw response text from AI
 * @returns {Object} Parsed JSON object
 * @throws {Error} If JSON parsing fails after all cleanup attempts
 */
function cleanAndParseAIResponse(responseText) {
  let cleanedText = responseText.trim();

  // Strategy 1: Remove common Markdown code block wrappers
  if (cleanedText.startsWith("```json") && cleanedText.endsWith("```")) {
    cleanedText = cleanedText.substring(7, cleanedText.length - 3).trim();
  } else if (cleanedText.startsWith("```") && cleanedText.endsWith("```")) {
    cleanedText = cleanedText.substring(3, cleanedText.length - 3).trim();
  }

  // Strategy 2: Find the first '{' and last '}' to isolate the JSON object
  const firstBrace = cleanedText.indexOf('{');
  const lastBrace = cleanedText.lastIndexOf('}');
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    cleanedText = cleanedText.substring(firstBrace, lastBrace + 1);
  }

  // Strategy 3: Remove any leading/trailing non-JSON characters
  cleanedText = cleanedText.trim();

  // Attempt to parse the cleaned text
  try {
    return JSON.parse(cleanedText);
  } catch (e) {
    throw new Error(`Failed to parse cleaned JSON: ${e.message}. Cleaned Text: ${cleanedText}`);
  }
}

/**
 * Validate that all required columns exist in the sheet
 * @param {Array} headers - Array of column headers
 * @returns {Object} Object containing column indices or null if validation fails
 */
function validateSheetStructure(headers) {
  const requiredColumns = {
    status: 'Status',
    name: 'Name', 
    title: 'Title',
    company: 'Company',
    industry: 'Company Industry',
    description: 'Company Description',
    pain: 'Pain (guess)',
    project: 'Project Type',
    opener: 'Personalized Opener'
  };
  
  const columnIndices = {};
  const missingColumns = [];
  
  for (const [key, columnName] of Object.entries(requiredColumns)) {
    const index = headers.indexOf(columnName);
    if (index === -1) {
      missingColumns.push(columnName);
    } else {
      columnIndices[key] = index;
    }
  }
  
  if (missingColumns.length > 0) {
    SpreadsheetApp.getUi().alert(
      `Error: Missing required columns: ${missingColumns.join(', ')}\n\n` +
      'Please ensure your sheet has all required columns with exact names.'
    );
    return null;
  }
  
  return columnIndices;
}

/**
 * Generate AI prompt for lead analysis
 * @param {Object} leadData - Object containing lead information
 * @returns {string} Formatted prompt for AI
 */
function generateLeadAnalysisPrompt(leadData) {
  const { name, title, company, industry, description } = leadData;
  
  return `**ROLE:** You are a sales development expert for an AI Automation Agency. Analyze a new lead to find the perfect outreach angle.

**CONTEXT:** Based on the following data, generate a JSON object with three keys: "pain_guess", "project_type", and "personalized_opener".

**LEAD DATA:**
- Name: ${name}
- Title: ${title}  
- Company: ${company}
- Company Industry: ${industry}
- Company Description: ${description}

**INSTRUCTIONS:**
1. **pain_guess:** A likely business pain they face (under 15 words).
2. **project_type:** ONE from: "${CONFIG.PROJECT_TYPES.join('", "')}".
3. **personalized_opener:** A single, compelling opening sentence for an email.

**OUTPUT FORMAT:** Respond with ONLY the JSON object. No other text, no markdown code blocks.`;
}

// ================================
// MAIN FUNCTIONALITY
// ================================

/**
 * Create custom menu when spreadsheet opens
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🤖 AI Lead Tools')
    .addItem('Refine Scraped Leads', 'refineLeads')
    .addItem('Show Setup Instructions', 'showSetupInstructions')
    .addToUi();
}

/**
 * Show setup instructions to the user
 */
function showSetupInstructions() {
  const instructions = `LinkedIn Lead Refinement Setup Instructions:

1. GEMINI API KEY:
   - Go to Project Settings (gear icon) 
   - Add Script Property: GEMINI_API_KEY
   - Value: Your Google Gemini API key

2. REQUIRED COLUMNS:
   Your sheet must have these exact column names:
   - Status, Name, Title, Company
   - Company Industry, Company Description  
   - Pain (guess), Project Type, Personalized Opener

3. USAGE:
   - Mark leads as "SCRAPED" in Status column
   - Run "Refine Scraped Leads" from the AI Tools menu
   - The script will analyze each lead and fill in the missing data

4. TROUBLESHOOTING:
   - Check execution logs: View > Execution transcript
   - Ensure API key is set correctly
   - Verify all required columns exist

Need help? Check the documentation in the GitHub repository.`;

  SpreadsheetApp.getUi().alert('Setup Instructions', instructions, SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Process a single lead with AI analysis
 * @param {Object} leadData - Lead information
 * @param {number} rowIndex - Row index in sheet (0-based)
 * @param {Object} columns - Column indices object
 * @param {Sheet} sheet - Google Sheets object
 * @returns {boolean} Success status
 */
function processLead(leadData, rowIndex, columns, sheet) {
  const rowNumber = rowIndex + 1; // Convert to 1-based for sheet operations
  
  try {
    // Mark as in progress
    sheet.getRange(rowNumber, columns.status + 1).setValue(CONFIG.STATUS.IN_PROGRESS);
    
    // Generate AI prompt
    const prompt = generateLeadAnalysisPrompt(leadData);
    
    // Call Gemini API
    const response = callGeminiAPI(prompt);
    
    if (!response.success) {
      console.error(`API Error for row ${rowNumber}:`, response.error);
      sheet.getRange(rowNumber, columns.status + 1).setValue(CONFIG.STATUS.FAILED_API_ERROR);
      return false;
    }
    
    // Parse AI response
    let analysisResult;
    try {
      analysisResult = cleanAndParseAIResponse(response.data);
    } catch (parseError) {
      console.error(`JSON Parse Error for row ${rowNumber}:`, parseError.message);
      console.error('Raw AI Output:', response.data);
      sheet.getRange(rowNumber, columns.status + 1).setValue(CONFIG.STATUS.FAILED_INVALID_JSON);
      return false;
    }
    
    // Update sheet with results
    sheet.getRange(rowNumber, columns.pain + 1).setValue(analysisResult.pain_guess || 'N/A');
    sheet.getRange(rowNumber, columns.project + 1).setValue(analysisResult.project_type || 'N/A');
    sheet.getRange(rowNumber, columns.opener + 1).setValue(analysisResult.personalized_opener || 'N/A');
    sheet.getRange(rowNumber, columns.status + 1).setValue(CONFIG.STATUS.COMPLETE);
    
    console.log(`Successfully processed row ${rowNumber}: ${leadData.name}`);
    return true;
    
  } catch (error) {
    console.error(`Unexpected error processing row ${rowNumber}:`, error);
    sheet.getRange(rowNumber, columns.status + 1).setValue(CONFIG.STATUS.FAILED_SCRIPT_ERROR);
    return false;
  }
}

/**
 * Call Google Gemini API with error handling
 * @param {string} prompt - Prompt to send to AI
 * @returns {Object} Response object with success status and data/error
 */
function callGeminiAPI(prompt) {
  const options = {
    method: 'POST',
    contentType: 'application/json',
    headers: {
      'x-goog-api-key': GEMINI_API_KEY,
    },
    payload: JSON.stringify({
      contents: [{
        parts: [{
          text: prompt
        }]
      }]
    }),
    muteHttpExceptions: true
  };

  try {
    const response = UrlFetchApp.fetch(CONFIG.GEMINI_API_URL, options);
    const httpCode = response.getResponseCode();

    if (httpCode !== 200) {
      return {
        success: false,
        error: `HTTP ${httpCode}: ${response.getContentText()}`
      };
    }

    const json = JSON.parse(response.getContentText());

    // Check for API error object
    if (json.error) {
      return {
        success: false,
        error: `API Error: ${JSON.stringify(json.error)}`
      };
    }

    // Check if content was generated
    if (!json.candidates || json.candidates.length === 0 || 
        !json.candidates[0].content || !json.candidates[0].content.parts || 
        json.candidates[0].content.parts.length === 0) {
      return {
        success: false,
        error: 'No content generated by AI'
      };
    }

    return {
      success: true,
      data: json.candidates[0].content.parts[0].text
    };

  } catch (error) {
    return {
      success: false,
      error: `Request failed: ${error.message}`
    };
  }
}

/**
 * Main function to refine all scraped leads
 */
function refineLeads() {
  // Validate API key
  if (!GEMINI_API_KEY || GEMINI_API_KEY === "YOUR_GEMINI_API_KEY") {
    SpreadsheetApp.getUi().alert(
      'Error: GEMINI_API_KEY not configured',
      'Please set your GEMINI_API_KEY in Project Settings > Script Properties.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();
  
  if (data.length < 2) {
    SpreadsheetApp.getUi().alert('Error: No data found in the sheet.');
    return;
  }
  
  const headers = data[0];
  
  // Validate sheet structure
  const columns = validateSheetStructure(headers);
  if (!columns) {
    return; // Error already shown in validateSheetStructure
  }

  // Initialize counters and timing
  let processedCount = 0;
  let errorCount = 0;
  let skippedCount = 0;
  const startTime = Date.now();

  console.log(`Starting lead refinement for ${data.length - 1} rows`);

  // Process each row
  for (let i = 1; i < data.length; i++) {
    // Check execution time limit
    if (Date.now() - startTime > CONFIG.MAX_EXECUTION_TIME) {
      console.warn('Approaching execution time limit. Stopping to prevent timeout.');
      SpreadsheetApp.getUi().alert(
        'Script stopped to prevent timeout. Please run again to process remaining leads.',
        'Execution Time Limit',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
      break;
    }

    const row = data[i];
    const status = row[columns.status];

    // Only process rows with "SCRAPED" status
    if (status !== CONFIG.STATUS.SCRAPED) {
      skippedCount++;
      continue;
    }

    // Extract and clean lead data
    const leadData = {
      name: (row[columns.name] || '').toString().trim(),
      title: (row[columns.title] || '').toString().trim(),
      company: (row[columns.company] || '').toString().trim(),
      industry: (row[columns.industry] || '').toString().trim(),
      description: (row[columns.description] || '').toString().trim()
    };

    // Skip if essential data is missing
    if (!leadData.name || !leadData.company) {
      console.warn(`Skipping row ${i + 1}: Missing essential data (name or company)`);
      skippedCount++;
      continue;
    }

    // Process the lead
    if (processLead(leadData, i, columns, sheet)) {
      processedCount++;
    } else {
      errorCount++;
    }
  }

  // Show completion summary
  const message = `✅ Lead refinement complete!
  
Processed: ${processedCount}
Errors: ${errorCount}  
Skipped: ${skippedCount}

Check the Status column for detailed results.`;

  SpreadsheetApp.getUi().alert('Refinement Complete', message, SpreadsheetApp.getUi().ButtonSet.OK);
  console.log(message);
}