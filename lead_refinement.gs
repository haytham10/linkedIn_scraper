// === CONFIGURATION ===
const GEMINI_API_KEY = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');

// === CUSTOM MENU ===
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🤖 AI Tools')
    .addItem('Refine Scraped Leads', 'refineLeads')
    .addToUi();
}

// === FUNCTION TO CLEAN AI RESPONSE ===
function cleanAndParseAIResponse(responseText) {
  let cleanedText = responseText.trim();

  if (cleanedText.startsWith("```json") && cleanedText.endsWith("```")) {
    cleanedText = cleanedText.substring(7, cleanedText.length - 3).trim();
  } else if (cleanedText.startsWith("```") && cleanedText.endsWith("```")) {
    cleanedText = cleanedText.substring(3, cleanedText.length - 3).trim();
  }

  const firstBrace = cleanedText.indexOf('{');
  const lastBrace = cleanedText.lastIndexOf('}');
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    cleanedText = cleanedText.substring(firstBrace, lastBrace + 1);
  }

  cleanedText = cleanedText.trim();

  try {
    return JSON.parse(cleanedText);
  } catch (e) {
    throw new Error(`Failed to parse cleaned JSON: ${e.message}. Cleaned Text: ${cleanedText}`);
  }
}

// === MAIN FUNCTION ===
function refineLeads() {
  if (!GEMINI_API_KEY || GEMINI_API_KEY === "YOUR_GEMINI_API_KEY") {
    SpreadsheetApp.getUi().alert("Error: Please set your GEMINI_API_KEY in Script Properties.");
    return;
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();
  const headers = data[0];

  const statusIndex   = headers.indexOf("Status");
  const nameIndex     = headers.indexOf("Name");
  const titleIndex    = headers.indexOf("Title");
  const companyIndex  = headers.indexOf("Company");
  const industryIndex = headers.indexOf("Company Industry");
  const descIndex     = headers.indexOf("Company Description");

  const painIndex     = headers.indexOf("Pain (guess)");
  const projectIndex  = headers.indexOf("Project Type");
  const openerIndex   = headers.indexOf("Personalized Opener");

  if ([statusIndex, nameIndex, titleIndex, companyIndex, industryIndex, descIndex, painIndex, projectIndex, openerIndex].some(idx => idx === -1)) {
    SpreadsheetApp.getUi().alert("Error: Missing required columns.");
    return;
  }

  let processedCount = 0;
  let errorCount = 0;

  const startTime = Date.now();
  const maxExecutionTime = 4.5 * 60 * 1000;

  for (let i = 1; i < data.length; i++) {
    if (Date.now() - startTime > maxExecutionTime) {
      SpreadsheetApp.getUi().alert("⏱ Stopped before timeout. Run again to continue.");
      break;
    }

    const row = data[i];
    const status = row[statusIndex];
    if (status !== "SCRAPED") continue;

    const name        = (row[nameIndex] || "").toString().trim();
    const title       = (row[titleIndex] || "").toString().trim();
    const company     = (row[companyIndex] || "").toString().trim();
    const industry    = (row[industryIndex] || "").toString().trim();
    const description = (row[descIndex] || "").toString().trim();

    // === NEW PROMPT WITH "NO —" RULE ===
    const prompt = `
    ROLE: You are a skilled sales strategist with over 10 years of experience in cold email prospecting. 
    You are asked to create three outputs: "pain_guess", "project_type", and "personalized_opener", formatted as JSON.

    LEAD DATA:
    - Name: ${name}
    - Title: ${title}
    - Company: ${company}
    - Company Industry: ${industry}
    - Company Description: ${description}

    INSTRUCTIONS:
    1. "pain_guess":
      - Write a likely business pain for the company.
      - Keep it short, direct, under 8 words.
      - Phrase it as a fragment, not a full sentence.
      - Example: "manual reporting", "slow client onboarding", "disconnected data tools".

    2. "project_type":  
      - Select ONE from this fixed set:  
        "Automated Reporting", "CRM Data Sync", "Lead Nurturing", "Client Onboarding", "Internal Process Automation".

    3. "personalized_opener":  
      - Write 1–2 short, natural sentences as an icebreaker based on the company description.  
      - Warm, conversational, but not hyped or formal.  
      - Be specific and relevant to their description, using plain English.  
      - Do not restate or copy their description. Infer, reframe, or lightly reference.  
      - Avoid generic praise, assumptions about success, or over‑positivity.  
      - Do not use: clichés, "I noticed", "your approach", "impressive", "leading provider", "excited to".  
      - No greetings, fluff, or filler.  
      - Do not include numbers, statistics, or emojis.  
      - If description is empty or generic (e.g. "IT Services"), return "" (empty string).  
      - ⚠️ Do NOT use em‑dashes (—). Only use plain punctuation.

    OUTPUT FORMAT:
    Return ONLY a valid JSON object:

    {
      "pain_guess": "...",
      "project_type": "...",
      "personalized_opener": "..."
    }
`;

    try {
      const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent';
      const options = {
        method: 'POST',
        contentType: 'application/json',
        headers: { 'x-goog-api-key': GEMINI_API_KEY },
        payload: JSON.stringify({
          contents: [{ parts: [{ text: prompt }]}]
        }),
        muteHttpExceptions: true
      };

      const response = UrlFetchApp.fetch(url, options);
      const httpCode = response.getResponseCode();

      if (httpCode !== 200) {
        console.error("API error row " + (i+1) + ":", response.getContentText());
        sheet.getRange(i + 1, statusIndex + 1).setValue("FAILED - API Error");
        errorCount++;
        continue;
      }

      const json = JSON.parse(response.getContentText());
      if (!json.candidates || !json.candidates.length) {
        sheet.getRange(i + 1, statusIndex + 1).setValue("FAILED - No Output");
        errorCount++;
        continue;
      }

      const resultText = json.candidates[0].content.parts[0].text.trim();
      let resultObj;
      try {
        resultObj = cleanAndParseAIResponse(resultText);
      } catch (error) {
        console.error("Parse error row " + (i+1), error.message, resultText);
        sheet.getRange(i + 1, statusIndex + 1).setValue("FAILED - Invalid JSON");
        errorCount++;
        continue;
      }

      sheet.getRange(i + 1, painIndex + 1).setValue(resultObj.pain_guess || "N/A");
      sheet.getRange(i + 1, projectIndex + 1).setValue(resultObj.project_type || "N/A");
      sheet.getRange(i + 1, openerIndex + 1).setValue(resultObj.personalized_opener || "N/A");

      sheet.getRange(i + 1, statusIndex + 1).setValue("COMPLETE");
      processedCount++;

    } catch (err) {
      console.error("Unexpected error row " + (i+1), err);
      sheet.getRange(i + 1, statusIndex + 1).setValue("FAILED - Script Error");
      errorCount++;
    }
  }

  SpreadsheetApp.getUi().alert(`✅ Refinement Complete!\nProcessed: ${processedCount}\nErrors: ${errorCount}`);
}