// Constants & setup (adjust based on your Gemini API details)
const properties = PropertiesService.getScriptProperties().getProperties();
const geminiApiKey = properties['GOOGLE_API_KEY'];
const geminiEndpoint = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${geminiApiKey}`;

function createStandardHeader() {
  return CardService.newCardHeader()
    .setTitle("Your Mail Buddy")
    .setImageUrl("https://cdn2.iconfinder.com/data/icons/metaverse-flat-5/60/Robot-Assistant-Meta-ai-bot-512.png");
}

function analyzeUnreadEmails(e) {
  var selectedLabelName = e.formInput.selectedLabel;

  if (!selectedLabelName) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification()
        .setText("Please select a label to continue."))
      .build();
  }

  selectedLabelName = selectedLabelName.replace('-', ' ')

  var unreadThreads = GmailApp.search('is:unread -label:' + selectedLabelName);

  var importantEmails = [];

  for (var i = 0; i < unreadThreads.length; i++) {
    var thread = unreadThreads[i];
    var messages = thread.getMessages();
    var latestMessage = messages[messages.length - 1];
    var messageBody = latestMessage.getPlainBody();

    try {
      var importanceScore = callGeminiWithStructuredOutput(messageBody);

      if (importanceScore === "Reached rate limit, try again later") {
        return CardService.newActionResponseBuilder()
          .setNotification(CardService.newNotification()
            .setText("Reached rate limit, try again later"))
          .build();
      }

      if (importanceScore >= 4) {
        thread.addLabel(GmailApp.getUserLabelByName(selectedLabelName));

        // Get a summary of the email using Gemini
        var summaryPrompt = "Summarize the following email in one sentence:\n\n" + messageBody;
        var summary = callGemini(summaryPrompt);

        if (summary === "Reached rate limit, try again later") {
          return CardService.newActionResponseBuilder()
            .setNotification(CardService.newNotification()
              .setText("Reached rate limit, try again later"))
            .build();
        }

        importantEmails.push({
          subject: latestMessage.getSubject(),
          from: latestMessage.getFrom(),
          summary: summary,
          messageId: latestMessage.getId()
        });
      }
    } catch (error) {
      console.error("Error analyzing email:", error);
    }
  }

  var card = CardService.newCardBuilder();
  card.setHeader(createStandardHeader());
  createImportantEmailsCard(importantEmails, card, e.gmail.accessToken);
  builtCard = card.build()


  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(builtCard))
    .setNotification(CardService.newNotification()  

      .setText("Unread emails analyzed for importance!"))
    .build();
}

function createImportantEmailsCard(importantEmails, card, accessToken) {
  if (importantEmails.length > 0) {
    for (var i = 0; i < importantEmails.length; i++) {
      var section = CardService.newCardSection();
      var email = importantEmails[i];
      var textWidget = CardService.newTextParagraph()
        .setText("<b>Subject:</b> " + email.subject + "<br><br>" +
                 "<b>From: </b> " + email.from + "<br><br>" +
                 "<b>Summary:</b> " + email.summary);
      section.addWidget(textWidget);

      var button = CardService.newTextButton()
        .setText("Generate Draft Response")
        .setBackgroundColor("#FFD700")
        .setIcon(CardService.Icon.EMAIL)
        .setOnClickAction(CardService.newAction()
          .setFunctionName('generateResponseHomepage')
          .setParameters({
            accessToken: accessToken,
            messageId: email.messageId
          }))
        .setTextButtonStyle(CardService.TextButtonStyle.FILLED);
      section.addWidget(button);

      card.addSection(section);
    }
  } else {
    var section = CardService.newCardSection();
    section.addWidget(CardService.newTextParagraph().setText("No important emails found."));
  }
}

function onGmailMessageOpen(e) {
  // Get the ID of the currently opened message
  var messageId = e.gmail.messageId;

  // Fetch the message using the message ID
  var message = GmailApp.getMessageById(messageId);

  // Get the original message body
  var originalMessageBody = message.getPlainBody();

  // Get the subject and sender of the original email
  var originalSubject = message.getSubject();
  var originalSender = message.getFrom();

  // Get a summary of the email using Gemini
  var summaryPrompt = "Summarize the following email in one sentence:\n\n" + originalMessageBody;
  var summary = callGemini(summaryPrompt);

  if (summary === "Reached rate limit, try again later") {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification()
        .setText("Reached rate limit, try again later"))
      .build();
  }

  // Create the card
  var card = CardService.newCardBuilder();

  // Add the standard header to the card
  card.setHeader(createStandardHeader());

  // Create a single section for both email details and the button
  var section = CardService.newCardSection();

  // Add the email details widget
  var detailsWidget = CardService.newTextParagraph()
    .setText("<b>Subject:</b> " + originalSubject + "<br><br>" +
             "<b>From:</b> " + originalSender + "<br><br>" +
             "<b>Summary:</b> " + summary);
  section.addWidget(detailsWidget);

  // Add the "Generate Response" button
  var button = CardService.newTextButton()
    .setText("Generate Draft Response")
    .setBackgroundColor("#FFD700")
    .setIcon(CardService.Icon.EMAIL)
    .setOnClickAction(CardService.newAction().setFunctionName('generateResponse'))
    .setTextButtonStyle(CardService.TextButtonStyle.FILLED);
  section.addWidget(button);

  card.addSection(section);

  // Get the user's labels
  var labels = GmailApp.getUserLabels();

  // Create a dropdown for label selection
  var labelDropdown = CardService.newSelectionInput()
    .setType(CardService.SelectionInputType.DROPDOWN)
    .setTitle("Select Label for Important Emails")
    .setFieldName("selectedLabel");

  // Add labels to the dropdown
  labels.map(label => label.getName())
    .forEach(labelName => labelDropdown.addItem(labelName, labelName.replace(/ /g, '-'), false));
  section.addWidget(labelDropdown); // Add the dropdown to the same section

  var analyzeButton = CardService.newTextButton()
    .setText("Analyze Importance")
    .setIcon(CardService.Icon.FLIGHT_DEPARTURE)
    .setBackgroundColor("#FF3311")
    .setOnClickAction(CardService.newAction().setFunctionName('analyzeUnreadEmails'))
    .setTextButtonStyle(CardService.TextButtonStyle.FILLED);
  section.addWidget(analyzeButton);

  return card.build();
}

function callGemini(prompt) {
  const payload = {
    "contents": [
      {
        "parts": [
          {
            "text": prompt
          }
        ]
      }
    ]
  };

  const options = {
    'method': 'post',
    'contentType': 'application/json',
    'payload': JSON.stringify(payload)
  };

  try {
    const response = UrlFetchApp.fetch(geminiEndpoint, options);
    const data = JSON.parse(response);
    const content = data["candidates"][0]["content"]["parts"][0]["text"];
    return content;
  } catch (error) {
    if (error.message.includes('returned code 429')) {
      return "Reached rate limit, try again later";
    } else {
      console.error("Error calling Gemini:", error);
      throw error;
    }
  }
}

function callGeminiWithStructuredOutput(originalMessageBody) {
  var prompt =
    `On a scale of 1 to 5, with 1 being least important and 5 being most important, rate the importance of the following email. Automatically assign a low importance score (1 or 2) to auto-generated emails from companies. Assign the highest scores only to emails that are critical, demanding my immediate attention.
    Use this JSON reponse schema:
    {
      "importanceScore": [value],
    }
    Where [value] should be the integer value of the importance score.
    Email: ` + originalMessageBody;

  const payload = {
    "contents": [
      {
        "parts": [
          {
            "text": prompt
          }
        ]
      }
    ],
    "generationConfig": {
      "responseMimeType": "application/json"
    }
  };

  const options = {
    'method': 'post',
    'contentType': 'application/json',
    'payload': JSON.stringify(payload)
  };

  const response = UrlFetchApp.fetch(geminiEndpoint, options);

    try {
      const response = UrlFetchApp.fetch(geminiEndpoint, options);
      const data = JSON.parse(response);

      const content = JSON.parse(data["candidates"][0]["content"]["parts"][0]["text"]);
      const importanceScore = content.importanceScore;

      if (typeof importanceScore === 'number' && importanceScore >= 1 && importanceScore <= 5) {
        return importanceScore;
      } else {
        console.error("Invalid importance score from Gemini:", content);
        throw new Error("Invalid importance score from Gemini");
      }
    } catch (error) {
      if (error.message.includes('returned code 429')) {
        return "Reached rate limit, try again later";
      } else {
        console.error("Error calling Gemini:", error);
        throw error;
      }
    }
}

function generateResponseHomepage(e) {
  GmailApp.setCurrentMessageAccessToken(e.parameters.accessToken);

  var message = GmailApp.getMessageById(e.parameters.messageId);
  var originalMessageBody = message.getPlainBody();

var prompt = "Please generate a concise and professional response to the following email:\n\n"
  + originalMessageBody
  + "\n\n**Signature Instructions:** \
  * **DO NOT** include any placeholder names in the signature (like [Your Name]). \
  * **EXTRACT** the appropriate name to use in the signature directly from the original email. \
  * **CAREFULLY READ** the original email to identify the sender's name or any context clues that indicate the correct signature. \
  * If you are **unable to confidently determine the correct name**, omit the signature completely. \
  \n\n**Compose the response without including the email subject. DO NOT end the response with '[Your Name]'**.";
  var geminiResponse = callGemini(prompt);

  if (geminiResponse === "Reached rate limit, try again later") {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification()
        .setText("Reached rate limit, try again later"))
      .build();
  }

  message.createDraftReplyAll(geminiResponse);

  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification()
      .setText("Response draft created with Gemini!"))
    .build();
}

function generateResponse(e) {
  var accessToken = e.gmail.accessToken;
  GmailApp.setCurrentMessageAccessToken(accessToken);

  var messageId = e.gmail.messageId;
  var message = GmailApp.getMessageById(messageId);
  var originalMessageBody = message.getPlainBody();

  var prompt = "Please generate a concise and professional response to the following email:\n\n"
    + originalMessageBody
    + "\n\n**Signature Instructions:** \
    * **DO NOT** include any placeholder names in the signature (like [Your Name]). \
    * **EXTRACT** the appropriate name to use in the signature directly from the original email. \
    * **CAREFULLY READ** the original email to identify the sender's name or any context clues that indicate the correct signature. \
    * If you are **unable to confidently determine the correct name**, omit the signature completely. \
    \n\n**Compose the response without including the email subject. DO NOT end the response with '[Your Name]'**.";
  var geminiResponse = callGemini(prompt);

  if (geminiResponse === "Reached rate limit, try again later") {
          return CardService.newActionResponseBuilder()
            .setNotification(CardService.newNotification()
              .setText("Reached rate limit, try again later"))
            .build();
        }

  message.createDraftReplyAll(geminiResponse);

  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification()
      .setText("Response draft created with Gemini!"))
    .build();
}

function onHomepage(e) {
  var card = CardService.newCardBuilder();

  // Add the standard header to the card
  card.setHeader(createStandardHeader());

  var section = CardService.newCardSection();

  // Get the user's labels
  var labels = GmailApp.getUserLabels();

  // Create a dropdown for label selection
  var labelDropdown = CardService.newSelectionInput()
    .setType(CardService.SelectionInputType.DROPDOWN)
    .setTitle("Select Label to apply to Important Emails")
    .setFieldName("selectedLabel");

  // Add labels to the dropdown (excluding system labels)
  labels.map(label => label.getName())
        .forEach(labelName => labelDropdown.addItem(labelName, labelName.replace(/ /g, '-'), false));
  section.addWidget(labelDropdown);

  var analyzeButton = CardService.newTextButton()
    .setText("Analyze Importance")
    .setIcon(CardService.Icon.FLIGHT_DEPARTURE)
    .setBackgroundColor("#FF3311")
    .setOnClickAction(CardService.newAction().setFunctionName('analyzeUnreadEmails'))
    .setTextButtonStyle(CardService.TextButtonStyle.FILLED);
  section.addWidget(analyzeButton);
  card.addSection(section);

  return card.build();

}
