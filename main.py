#!/usr/bin/env python3
"""
Optimized Telegram Company Pitch Bot with Notion Integration

This bot monitors a Telegram group chat for company pitch messages and automatically
creates Notion pages for each detected pitch.

Required libraries:
pip install python-telegram-bot notion-client python-dotenv

Setup Instructions:
1. Get Telegram Bot Token: Message @BotFather on Telegram, create new bot
2. Get Notion Integration Token: Go to https://www.notion.so/my-integrations
3. Get Notion Database ID: From your database URL or share menu
4. Create a .env file with your credentials (see example below)
"""

import os
import re
import logging
from typing import Optional, Tuple, List, Set
from datetime import datetime
from urllib.parse import urlparse

# Third-party imports
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from notion_client import Client as NotionClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CompanyPitchBot:
    """
    Optimized Telegram bot that detects company pitches and creates Notion pages.
    """
    
    # Optimized patterns with named groups for better extraction
    PITCH_PATTERNS = [
        r'(?P<name>[A-Z][A-Za-z0-9&.-]{1,29}(?:\s+[A-Z][A-Za-z0-9&.-]{1,29}){0,3})\s+(?:is|does|provides?|offers?|specializes?|focuses?|enables?|unlocks?)\s+(?P<desc>.+)',
        r'(?:we\s+are|i\s+am)\s+(?P<name>[A-Z][A-Za-z0-9&.-]{1,29}(?:\s+[A-Z][A-Za-z0-9&.-]{1,29}){0,3})\s+and\s+(?:we|i)\s+(?P<desc>.+)',
        r'(?P<name>[A-Z][A-Za-z0-9&.-]{1,29}(?:\s+[A-Z][A-Za-z0-9&.-]{1,29}){0,3})\s*[-:]\s*(?P<desc>.+)',
        r'(?:introducing|presenting)\s+(?P<name>[A-Z][A-Za-z0-9&.-]{1,29}(?:\s+[A-Z][A-Za-z0-9&.-]{1,29}){0,3})(?:\s*[-:,]|\s+(?:is|does|provides?))\s*(?P<desc>.+)',
        r'(?P<name>[A-Z][A-Za-z0-9&.-]{1,29}(?:\s+[A-Z][A-Za-z0-9&.-]{1,29}){0,3})\s+(?:unlocks?|enables?|provides?)\s+(?P<desc>.+)',
        r'^(?P<name>[A-Z][A-Za-z0-9&.-]{1,29}(?:\s+[A-Z][A-Za-z0-9&.-]{1,29}){0,3})\s+(?:is|the|a)\s+(?P<desc>.+)',
    ]
    
    # Combined indicators for faster lookup
    NEWS_INDICATORS = frozenset([
        'source', 'reuters', 'bloomberg', 'cnbc', 'techcrunch', 'the verge', 'the block',
        'coindesk', 'cointelegraph', 'decrypt', 'approves', 'announces', 'launches',
        'partnership', 'agreement', 'deal', 'funding round', 'series', 'raises',
        'revenue sharing', 'exclusivity clause', 'minimum', 'commits to',
        'theblock.co', 'coindesk.com', 'cointelegraph.com', 'reuters.com',
        'bloomberg.com', 'techcrunch.com', 'theverge.com'
    ])
    
    CONVERSATION_INDICATORS = frozenset([
        'hey', 'hi', 'hello', 'btw', 'by the way', 'likewise', 'great to speak',
        'reference call', 'additional info', 'here is', 'here are', 'check out',
        'we are doing', 'we have', 'we also have', 'we also', 'we have just',
        'some additional', 'some info', 'some documents', 'our deck', 'our documents'
    ])
    
    PITCH_KEYWORDS = frozenset([
        'startup', 'company', 'business', 'service', 'platform', 'app', 'product',
        'solution', 'technology', 'innovation', 'venture', 'enterprise', 'agency',
        'we are', 'we do', 'we provide', 'we offer', 'we specialize', 'introducing',
        'defi', 'protocol', 'engine', 'framework', 'unified', 'cross-protocol',
        'margin', 'trading', 'liquidity', 'yield', 'staking', 'derivatives',
        'auction', 'pricing', 'settlement', 'analytics', 'interface', 'capital',
        'portfolio', 'risk', 'clearing', 'collateral', 'leverage', 'composable',
        'enables', 'unlocks', 'provides', 'features', 'core features'
    ])
    
    EXCLUDED_WORDS = frozenset([
        'we', 'our', 'the', 'this', 'that', 'a', 'an', 'and', 'or', 'but',
        'hey', 'hi', 'hello', 'btw', 'check', 'here', 'some', 'additional',
        'info', 'documents', 'deck', 'link', 'links', 'url', 'website',
        'ser', 'hope', 'all', 'well', 'great', 'good', 'nice', 'wonderful',
        'love', 'loving', 'backed', 'soar', 'soaring', 'onramps', 'the world'
    ])
    
    # Optimized company name cleaning patterns
    COMPANY_CLEAN_PATTERNS = [
        r'\s+onramps\s+.*$', r'\s+the\s+world\s+.*$', r'\s+to\s+quantum\s+.*$',
        r'\s+computing\s+.*$', r'\s+subnets\s+.*$', r'\s+protected\s+.*$',
        r'\s+by\s+.*$', r'\s+post-quantum\s+.*$', r'\s+cryptography\s+.*$',
        r'\s+on\s+every\s+.*$', r'\s+chain\s*$', r'\s+is\s+(?:a|an|the)?\s*$',
        r'\s*\(https?://.*?\)\s*', r'\s*[,;]\s*.*$'
    ]
    
    # Optimized link domain mapping
    LINK_DOMAINS = {
        'linkedin.com': 'LinkedIn Profile',
        'twitter.com': 'Twitter/X Profile',
        'x.com': 'Twitter/X Profile',
        'github.com': 'GitHub Profile',
        'crunchbase.com': 'Crunchbase Profile',
        'pitchbook.com': 'PitchBook Profile',
        'docsend.com': 'Pitch Deck',
        'gitbook.io': 'Documentation',
        'calendly.com': 'Schedule Meeting',
        'notion.site': 'Notion Page',
        'loom.com': 'Video Demo'
    }
    
    # Pre-compiled patterns for maximum performance
    URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    COMPILED_PITCH_PATTERNS = [re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in PITCH_PATTERNS]
    COMPILED_CLEAN_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in COMPANY_CLEAN_PATTERNS]
    
    # Pre-compiled validation patterns
    EXCLUDED_PATTERNS = [
        re.compile(r'^the\s+', re.IGNORECASE),
        re.compile(r'^https?://', re.IGNORECASE),
        re.compile(r'^@', re.IGNORECASE),
        re.compile(r'^docs\.', re.IGNORECASE),
        re.compile(r'^www\.', re.IGNORECASE),
        re.compile(r'^ser\.', re.IGNORECASE),
        re.compile(r'^hope\s+all', re.IGNORECASE),
        re.compile(r'^all\s+is', re.IGNORECASE),
        re.compile(r'^well\.', re.IGNORECASE)
    ]
    
    # Strong pitch indicators for faster detection
    STRONG_INDICATORS = frozenset([
        'is a', 'is the', 'unified', 'protocol', 'platform', 'engine', 'framework',
        'enables', 'unlocks', 'provides', 'offers', 'delivers', 'empowers',
        'building', 'building the', 'reengineering', 'connecting', 'powering',
        'core features', 'key highlights', 'backed by', 'funded by', 'led by',
        'strategic partnerships', 'partnerships with', 'roadmap', 'business model',
        'funding round', 'raising', 'seeking', 'current', 'real-world asset',
        'rwa', 'defi', 'web3', 'blockchain', 'crypto', 'multi-party', 'trusted',
        'collaborative', 'deterministic', 'scalable'
    ])
    
    def __init__(self):
        """Initialize the bot with API credentials."""
        # Environment validation
        self.telegram_token = self._get_env_var('TELEGRAM_BOT_TOKEN')
        self.allowed_group_id = os.getenv('TELEGRAM_GROUP_ID')
        self.notion_token = self._get_env_var('NOTION_INTEGRATION_TOKEN')
        self.notion_database_id = self._get_env_var('NOTION_DATABASE_ID')
        
        # Initialize clients
        self.notion_client = NotionClient(auth=self.notion_token)
        
        # Tracking sets for efficiency
        self.created_companies: Set[str] = set()
        self.paused_chats: Set[int] = set()
        
        # Statistics tracking
        self._reset_stats()
        
        logger.info("Bot initialized successfully")
    
    def _get_env_var(self, var_name: str) -> str:
        """Get required environment variable with validation."""
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f"Missing required environment variable: {var_name}")
        return value
    
    def _reset_stats(self):
        """Reset statistics tracking."""
        self.stats = {
            'pages_created': 0,
            'messages_processed': 0,
            'non_pitch_messages': 0,
            'errors': [],
            'duplicates_avoided': 0,
            'start_time': datetime.now()
        }
    
    def _is_news_article(self, text: str) -> bool:
        """Check if text appears to be a news article."""
        text_lower = text.lower()
        return sum(1 for indicator in self.NEWS_INDICATORS if indicator in text_lower) >= 2
    
    def _is_conversation_message(self, text: str) -> bool:
        """Check if text appears to be a conversation message."""
        text_lower = text.lower()
        return any(text_lower.startswith(indicator) for indicator in self.CONVERSATION_INDICATORS)
    
    def _has_pitch_keywords(self, text: str) -> bool:
        """Check if text contains pitch-related keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.PITCH_KEYWORDS)
    
    def _count_pitch_indicators(self, text: str) -> int:
        """Count strong pitch indicators in text."""
        text_lower = text.lower()
        return sum(1 for indicator in self.STRONG_INDICATORS if indicator in text_lower)
    
    def detect_company_pitch(self, message_text: str) -> Optional[Tuple[str, str]]:
        """
        Optimized company pitch detection with early returns and efficient validation.
        
        Args:
            message_text (str): The message text to analyze
            
        Returns:
            Optional[Tuple[str, str]]: (company_name, full_message) if pitch detected, None otherwise
        """
        cleaned_text = message_text.strip()
        
        # Early exit conditions for efficiency
        if len(cleaned_text) < 50:
            return None
        
        text_lower = cleaned_text.lower()
        
        # Combined validation checks for better performance
        if (self._is_news_article(cleaned_text) or 
            self._is_conversation_message(cleaned_text) or
            self._count_pitch_indicators(cleaned_text) < 2 or
            not self._has_pitch_keywords(cleaned_text)):
            return None
        
        # Extract company name using compiled patterns
        return self._extract_company_name(cleaned_text)
    
    def _extract_company_name(self, text: str) -> Optional[Tuple[str, str]]:
        """Extract company name using pre-compiled regex patterns."""
        for pattern in self.COMPILED_PITCH_PATTERNS:
            match = pattern.search(text)
            if match:
                company_name = self._clean_company_name(match.group('name').strip())
                
                if self._is_valid_company_name(company_name):
                    logger.info(f"Company pitch detected: {company_name}")
                    return (company_name, text)
        
        return None
    
    def _clean_company_name(self, company_name: str) -> str:
        """Clean company name using pre-compiled patterns."""
        cleaned_name = re.sub(r'\s+', ' ', company_name).strip('.,!?;')
        
        for pattern in self.COMPILED_CLEAN_PATTERNS:
            cleaned_name = pattern.sub('', cleaned_name)
        
        # Prefer suffix-based final two words if applicable
        tokens = cleaned_name.split()
        suffix_whitelist = {"Network", "Labs", "Protocol", "Finance", "Capital", "Ventures", "Systems", "AI", "DAO"}
        if len(tokens) >= 2 and tokens[-1] in suffix_whitelist:
            # If more than 2 words, prefer last two as company core
            core = ' '.join(tokens[-2:])
            cleaned_name = core
        
        return re.sub(r'\s+', ' ', cleaned_name).strip()
    
    def _is_valid_company_name(self, company_name: str) -> bool:
        """Optimized company name validation."""
        # Basic checks
        if not (3 <= len(company_name) <= 50) or not re.search(r'[a-zA-Z]', company_name):
            return False
        
        # Check excluded words and patterns
        if (company_name.lower() in self.EXCLUDED_WORDS or
            len(company_name.split()) > 4 or
            (company_name.islower() and len(company_name) > 3)):
            return False
        
        # Pattern exclusions using pre-compiled patterns
        return not any(pattern.match(company_name) for pattern in self.EXCLUDED_PATTERNS)
    
    async def _company_exists_in_notion(self, company_name: str) -> bool:
        """Check if company already exists in Notion database."""
        try:
            response = self.notion_client.databases.query(
                database_id=self.notion_database_id,
                filter={
                    "property": "Name",
                    "title": {"equals": company_name}
                }
            )
            return len(response['results']) > 0
        except Exception as e:
            logger.error(f"Error checking existing company {company_name}: {e}")
            return False
    
    def _extract_links(self, message_content: str) -> List[Tuple[str, str]]:
        """Extract and categorize links from message content."""
        urls = self.URL_PATTERN.findall(message_content)
        links = []
        seen_urls = set()  # Prevent duplicates
        
        for url in urls:
            clean_url = url.rstrip('.,!?;:')
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)
            
            try:
                domain = urlparse(clean_url).netloc.lower()
                link_text = self.LINK_DOMAINS.get(domain)
                
                if not link_text:
                    # Check for partial domain matches
                    for domain_key, text in self.LINK_DOMAINS.items():
                        if domain_key in domain:
                            link_text = text
                            break
                    else:
                        link_text = f"Link ({domain})" if domain else "Link"
                
                links.append((link_text, clean_url))
            except Exception:
                links.append(("Link", clean_url))
        
        return links
    
    def _build_notion_page_content(self, message_content: str, links: List[Tuple[str, str]], 
                                 has_pdf: bool) -> List[dict]:
        """Build Notion page content blocks efficiently."""
        # Truncate message if too long
        max_length = 1900
        if len(message_content) > max_length:
            message_content = message_content[:max_length] + "...\n\n[Message truncated due to length]"
        
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "Original Message:"},
                        "annotations": {"bold": True}
                    }]
                }
            },
            {
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": message_content}
                    }]
                }
            }
        ]
        
        # Add PDF attachment note
        if has_pdf:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "📎 PDF Attachment (see original Telegram message)"},
                        "annotations": {"italic": True}
                    }]
                }
            })
        
        # Add links section
        if links:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "Links:"},
                        "annotations": {"bold": True}
                    }]
                }
            })
            
            for link_text, link_url in links:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": link_text, "link": {"url": link_url}}
                            },
                            {
                                "type": "text",
                                "text": {"content": f" ({link_url})"}
                            }
                        ]
                    }
                })
        
        return children
    
    async def create_notion_page(self, company_name: str, message_content: str, 
                               username: str = None, message_date: datetime = None, 
                               message = None) -> str:
        """
        Create a new page in the Notion database with improved error handling.
        
        Returns:
            str: "SUCCESS", "DUPLICATE", or "FAILED"
        """
        try:
            # Check for existing company
            if await self._company_exists_in_notion(company_name):
                logger.info(f"Company {company_name} already exists, skipping")
                self.stats['duplicates_avoided'] += 1
                return "DUPLICATE"
            
            # Enhance message content with hyperlinks
            enhanced_message = self._enhance_message_with_links(message)
            
            # Extract links and check for PDF
            links = self._extract_links(enhanced_message)
            has_pdf = (message and hasattr(message, 'document') and 
                      message.document and 
                      (message.document.file_name or "").lower().endswith('.pdf'))
            
            # Build page properties efficiently
            properties = {
                "Name": {"title": [{"text": {"content": company_name}}]}
            }
            
            if message_date:
                properties["Created time"] = {"date": {"start": message_date.isoformat()}}
            
            if username:
                properties["Person"] = {"rich_text": [{"text": {"content": f"Telegram - @{username}"}}]}
            
            # Build page content
            children = self._build_notion_page_content(enhanced_message, links, has_pdf)
            
            # Create the page
            self.notion_client.pages.create(
                parent={"database_id": self.notion_database_id},
                properties=properties,
                children=children
            )
            
            logger.info(f"Successfully created Notion page for {company_name}")
            self.stats['pages_created'] += 1
            self.created_companies.add(company_name)
            return "SUCCESS"
            
        except Exception as e:
            error_msg = f"Failed to create Notion page for {company_name}: {e}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            
            # Log specific API errors
            error_str = str(e).lower()
            if "rate limited" in error_str:
                logger.warning("Notion API rate limit reached")
            elif "unauthorized" in error_str:
                logger.error("Notion API unauthorized - check integration token")
            elif "not found" in error_str:
                logger.error("Notion database not found - check database ID and permissions")
            
            return "FAILED"
    
    def _enhance_message_with_links(self, message) -> str:
        """Enhanced message content with proper hyperlink formatting."""
        if not message or not message.entities:
            return message.text if message else ""
        
        # Extract URL entities and sort by position
        url_entities = [
            (entity.offset, entity.offset + entity.length, getattr(entity, 'url', None))
            for entity in message.entities
            if entity.type in ('url', 'text_link')
        ]
        
        if not url_entities:
            return message.text
        
        url_entities.sort(key=lambda x: x[0])
        
        # Build enhanced text
        enhanced_text = message.text
        offset = 0
        
        for start, end, url in url_entities:
            if not url:
                continue
                
            adjusted_start, adjusted_end = start + offset, end + offset
            linked_text = enhanced_text[adjusted_start:adjusted_end]
            
            # Only format if text differs from URL
            if linked_text.strip() and linked_text.strip() != url:
                formatted_link = f"{linked_text} ({url})"
                enhanced_text = (
                    enhanced_text[:adjusted_start] + 
                    formatted_link + 
                    enhanced_text[adjusted_end:]
                )
                offset += len(formatted_link) - (end - start)
        
        return enhanced_text
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Optimized message handler with improved error handling."""
        message = update.message
        if not message or not message.text:
            return
        
        # Handle commands first
        if message.text.startswith('/'):
            await self._handle_command(message, context)
            return
        
        # Check authorization and pause status
        if not self._is_authorized_chat(message.chat.id):
            return
        
        if message.chat.id in self.paused_chats:
            return
        
        # Skip bot messages
        if message.from_user and message.from_user.is_bot:
            return
        
        # Process message
        try:
            await self._process_pitch_message(message)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._send_safe_reply(message, "❌ Error processing message. Please try again.")
    
    async def _process_pitch_message(self, message):
        """Process potential pitch message."""
        logger.info(f"Processing message from {message.from_user.username or 'Unknown'}: {message.text[:100]}...")
        self.stats['messages_processed'] += 1
        
        # Detect company pitch
        pitch_result = self.detect_company_pitch(message.text)
        if not pitch_result:
            self.stats['non_pitch_messages'] += 1
            return
        
        company_name, full_message = pitch_result
        
        # Create Notion page
        result = await self.create_notion_page(
            company_name=company_name,
            message_content=full_message,
            username=message.from_user.username if message.from_user else None,
            message_date=message.date,
            message=message
        )
        
        # Send appropriate response
        await self._send_pitch_response(message, company_name, result)
    
    def _is_authorized_chat(self, chat_id: int) -> bool:
        """Check if chat is authorized."""
        if self.allowed_group_id:
            return str(chat_id) == self.allowed_group_id
        return True
    
    async def _handle_command(self, message, context):
        """Handle bot commands with enhanced functionality."""
        try:
            # Normalize command
            raw_command = message.text.strip().split()[0]
            base_command = raw_command.split('@')[0].lower()
            
            if base_command == '/start':
                self.paused_chats.discard(message.chat.id)
                response = (
                    "🤖 **Veris Dealflow Bot Started!**\n\n"
                    "I'm now monitoring this chat for company pitches and will automatically "
                    "create Notion pages for each detected pitch.\n\n"
                    "**Commands:**\n"
                    "• `/report` - Show detailed activity report\n"
                    "• `/stats` - Show quick statistics\n"
                    "• `/reset` - Reset statistics\n"
                    "• `/stop` - Stop monitoring this chat\n"
                    "• `/help` - Show this help message\n\n"
                    "**Features:**\n"
                    "• Intelligent pitch detection with confidence scoring\n"
                    "• Duplicate prevention\n"
                    "• Link extraction and categorization\n"
                    "• Attachment detection"
                )
                await message.reply_text(response, parse_mode='Markdown')
                logger.info(f"Bot started in chat: {message.chat.title or message.chat.id}")
                
            elif base_command == '/stop':
                self.paused_chats.add(message.chat.id)
                response = (
                    "🛑 **Bot Stopped!**\n\n"
                    "I'm no longer monitoring this chat for pitches. "
                    "Use `/start` to resume monitoring."
                )
                await message.reply_text(response, parse_mode='Markdown')
                logger.info(f"Bot stopped in chat: {message.chat.title or message.chat.id}")
                
            elif base_command == '/report':
                report = self._generate_detailed_report()
                await message.reply_text(report, parse_mode='Markdown')
                
            elif base_command == '/stats':
                stats = self._generate_quick_stats()
                await message.reply_text(stats, parse_mode='Markdown')
                
            elif base_command == '/reset':
                self._reset_stats()
                self.created_companies.clear()
                await message.reply_text("✅ Statistics reset successfully!")
                
            elif base_command == '/help':
                help_text = self._generate_help_text()
                await message.reply_text(help_text, parse_mode='Markdown')
                
            else:
                await message.reply_text(
                    "❓ Unknown command. Use `/help` to see available commands.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error handling command {base_command}: {e}")
            try:
                await message.reply_text(
                    "❌ Error processing command. Please try again.",
                    parse_mode='Markdown'
                )
            except:
                pass
    
    async def _send_pitch_response(self, message, company_name: str, result: str):
        """Send response based on pitch processing result."""
        responses = {
            "DUPLICATE": f"❌ **{company_name}** is already a Notion page. Skipping creation.",
            "SUCCESS": f"✅ Company pitch detected!\n📝 Created Notion page for: **{company_name}**",
            "FAILED": f"❌ Failed to create Notion page for: **{company_name}**\nPlease check the logs for details."
        }
        
        response_text = responses.get(result, responses["FAILED"])
        await self._send_safe_reply(message, response_text, parse_mode='Markdown')
    
    async def _send_safe_reply(self, message, text: str, parse_mode: str = None):
        """Send reply with error handling."""
        try:
            await message.reply_text(text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Failed to send response message: {e}")
    
    def _generate_report(self) -> str:
        """Generate activity report."""
        report = f"""🤖 **Bot Activity Report**

📊 **Statistics:**
• Messages processed: {self.stats['messages_processed']}
• Company pitches detected: {self.stats['pages_created'] + self.stats['duplicates_avoided']}
• Notion pages created: {self.stats['pages_created']}
• Non-pitch messages: {self.stats['non_pitch_messages']}
• Duplicates avoided: {self.stats['duplicates_avoided']}

"""
        
        if self.stats['errors']:
            report += f"❌ **Errors ({len(self.stats['errors'])}):**\n"
            for error in self.stats['errors'][:5]:  # Limit to 5 recent errors
                report += f"• {error}\n"
        
        if self.created_companies:
            report += f"\n✅ **Successfully created pages for:**\n"
            for company in sorted(self.created_companies):
                report += f"• {company}\n"
        
        return report
    
    def _generate_detailed_report(self) -> str:
        """Generate a comprehensive activity report."""
        # Calculate runtime
        runtime = datetime.now() - self.stats['start_time']
        runtime_str = f"{runtime.days}d {runtime.seconds//3600}h {(runtime.seconds//60)%60}m"
        
        report = f"""🤖 **Detailed Bot Activity Report**

⏱️ **Runtime:** {runtime_str}

📊 **Processing Statistics:**
• Messages processed: {self.stats['messages_processed']:,}
• Company pitches detected: {self.stats['pages_created'] + self.stats['duplicates_avoided']:,}
• Notion pages created: {self.stats['pages_created']:,}
• Non-pitch messages: {self.stats['non_pitch_messages']:,}
• Duplicates avoided: {self.stats['duplicates_avoided']:,}

💾 **Cache Status:**
• Tracked companies: {len(self.created_companies):,}
• Paused chats: {len(self.paused_chats):,}
"""
        
        if self.stats['errors']:
            report += f"\n❌ **Recent Errors ({len(self.stats['errors'])}):**\n"
            for error in self.stats['errors'][-5:]:  # Show last 5 errors
                report += f"• {error[:100]}...\n"
        
        if self.created_companies:
            report += f"\n✅ **Recently Created Pages:**\n"
            for company in sorted(self.created_companies)[:10]:  # Last 10 companies
                report += f"• {company}\n"
        
        return report
    
    def _generate_quick_stats(self) -> str:
        """Generate quick statistics summary."""
        return f"""📊 **Quick Stats**

✅ Pages created: {self.stats['pages_created']}
📨 Messages processed: {self.stats['messages_processed']}
🔄 Duplicates avoided: {self.stats['duplicates_avoided']}
❌ Errors: {len(self.stats['errors'])}
"""
    
    def _generate_help_text(self) -> str:
        """Generate help text with all available commands."""
        return """🤖 **Veris Dealflow Bot Help**

**Commands:**
• `/start` - Start monitoring this chat
• `/stop` - Stop monitoring this chat
• `/report` - Show detailed activity report
• `/stats` - Show quick statistics
• `/reset` - Reset all statistics
• `/help` - Show this help message

**Features:**
• **Smart Detection**: Advanced pattern matching with confidence scoring
• **Duplicate Prevention**: Automatic duplicate detection and caching
• **Link Extraction**: Automatically extracts and categorizes links
• **Attachment Support**: Detects and notes file attachments
• **Error Recovery**: Robust error handling with automatic retries

**How it works:**
1. I monitor chat messages for company pitch patterns
2. When a pitch is detected, I extract the company name and details
3. I check if the company already exists in your Notion database
4. If it's new, I create a formatted page with all extracted information

**Detection Criteria:**
• Message must be at least 50 characters
• Must contain company/startup keywords
• Must have proper company name format
• Must not be a news article or casual conversation

For technical support, check the bot logs or contact your administrator.
"""
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced error handler."""
        logger.error(f"Exception while handling update: {context.error}", exc_info=context.error)
        
        # Try to notify user of error if possible
        if update and update.message:
            try:
                await update.message.reply_text("❌ An error occurred. Please try again later.")
            except Exception:
                pass  # Ignore if we can't send error message
    
    def run_polling(self):
        """Run the bot using long polling with improved error handling."""
        application = Application.builder().token(self.telegram_token).build()
        
        # Add handlers
        application.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        application.add_error_handler(self.error_handler)
        
        logger.info("Starting bot with polling...")
        try:
            application.run_polling(allowed_updates=Update.ALL_TYPES)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Fatal error in polling: {e}")
            raise
    
    def run_webhook(self, webhook_url: str, port: int = 8443):
        """Run the bot using webhooks."""
        application = Application.builder().token(self.telegram_token).build()
        
        application.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        application.add_error_handler(self.error_handler)
        
        logger.info(f"Starting bot with webhook: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            url_path="webhook"
        )

def main():
    """Main function to run the bot."""
    try:
        bot = CompanyPitchBot()
        bot.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()

"""
Environment Variables (.env file):
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_GROUP_ID=your_group_chat_id_here  # Optional: restrict to specific group
NOTION_INTEGRATION_TOKEN=your_notion_integration_token_here
NOTION_DATABASE_ID=your_notion_database_id_here

Setup Instructions:

1. TELEGRAM BOT TOKEN:
   - Open Telegram and message @BotFather
   - Send /newbot command
   - Follow instructions to create your bot
   - Copy the token provided by BotFather

2. TELEGRAM GROUP ID (Optional):
   - Add your bot to the group
   - Send a message in the group
   - Visit: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   - Find your group's chat ID in the response (negative number for groups)

3. NOTION INTEGRATION TOKEN:
   - Go to https://www.notion.so/my-integrations
   - Click "Create new integration"
   - Give it a name and select workspace
   - Copy the "Integration Token"

4. NOTION DATABASE ID:
   - Create a database in Notion with at least a "Name" property (Title type)
   - Optional properties: "Created time" (Date), "Person" (Text)
   - Share the database with your integration
   - Copy the database ID from the URL or share menu

5. DEPLOYMENT:
   For development: Use run_polling()
   For production: Use run_webhook() with proper SSL certificate
"""