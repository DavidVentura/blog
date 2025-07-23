from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt

from generate import PostMetadata


def analyze_posts_with_gaps(directory):
    """Analyze all markdown posts including time gaps between posts."""
    yearly_stats = defaultdict(lambda: {'posts': 0, 'total_words': 0})
    all_posts = []
    
    # Find all markdown files and collect their dates
    for post_path in Path(directory).glob('*/POST.md'):
        with open(post_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        post_data = PostMetadata.from_text(content)
        if post_data.incomplete:
            continue
            
        year = post_data.date.year
        rest = "\n".join(content.split("---")[2:])
        # there is a little bit of html counted as words (<img src=...>)
        # maybe render this + read it back?
        # more important would be to count code-words and non-code words separately
        wc = len(str(rest).split())
            
        # Store post information
        all_posts.append({
            'date': post_data.date,
            'word_count': wc
        })
        
        # Update yearly statistics
        yearly_stats[year]['posts'] += 1
        yearly_stats[year]['total_words'] += wc
    
    # Sort posts by date
    all_posts.sort(key=lambda x: x['date'])
    
    # Calculate days between posts
    gaps = []
    dates = []
    for i in range(1, len(all_posts)):
        gap = (all_posts[i]['date'] - all_posts[i-1]['date']).days
        gaps.append(gap)
        dates.append(all_posts[i]['date'])
    
    # Calculate yearly stats as before
    results = []
    for year, stats in sorted(yearly_stats.items()):
        avg_words = stats['total_words'] / stats['posts'] if stats['posts'] > 0 else 0
        results.append({
            'year': year,
            'posts': stats['posts'],
            'total_words': stats['total_words'],
            'avg_words_per_post': round(avg_words, 2)
        })
    
    return results, (dates, gaps)


def create_and_save_plots(stats, gap_data):
    """Create and save individual plots as SVG files."""
    # Extract data for plotting
    years = [stat['year'] for stat in stats]  # Keep years as integers
    years_str = [str(year) for year in years]  # String version for labels
    posts = [stat['posts'] for stat in stats]
    avg_words = [stat['avg_words_per_post'] for stat in stats]
    total_words = [stat['total_words'] for stat in stats]

    # Common style settings
    plt.style.use('default')
    plot_kwargs = {
        'figsize': (10, 6),
        'dpi': 300
    }
    
    # 1. Posts per Year
    fig, ax = plt.subplots(**plot_kwargs)
    bars = ax.bar(years, posts, color='#2196F3', alpha=0.7)
    ax.set_title('Posts per Year', pad=15, fontsize=14)
    ax.set_xlabel('Year', fontsize=12)
    ax.set_ylabel('Number of Posts', fontsize=12)
    ax.set_xticks(years)
    ax.set_xticklabels(years_str)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig('posts_per_year.svg', format='svg', bbox_inches='tight')
    plt.close()
    
    # 2. Average Words per Post
    fig, ax = plt.subplots(**plot_kwargs)
    ax.plot(years, avg_words, marker='o', color='#4CAF50', linewidth=2)
    ax.set_title('Average Words per Post', pad=15, fontsize=14)
    ax.set_xlabel('Year', fontsize=12)
    ax.set_ylabel('Words', fontsize=12)
    ax.set_xticks(years)
    ax.set_xticklabels(years_str)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Add value labels
    for x, y in zip(years, avg_words):
        ax.text(x, y, f'{int(y)}', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig('avg_words_per_post.svg', format='svg', bbox_inches='tight')
    plt.close()
    
    # 3. Total Words per Year
    fig, ax = plt.subplots(**plot_kwargs)
    bars = ax.bar(years, total_words, color='#FF9800', alpha=0.7)
    ax.set_title('Total Words per Year', pad=15, fontsize=14)
    ax.set_xlabel('Year', fontsize=12)
    ax.set_ylabel('Words', fontsize=12)
    ax.set_xticks(years)
    ax.set_xticklabels(years_str)
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig('total_words_per_year.svg', format='svg', bbox_inches='tight')
    plt.close()
    
    # 4. Days Since Last Post
    dates, gaps = gap_data
    if dates and gaps:
        fig, ax = plt.subplots(**plot_kwargs)
        ax.plot(dates, gaps, marker='o', color='#9C27B0', linewidth=2, markersize=4)
        ax.set_title('Days Since Last Post', pad=15, fontsize=14)
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Days', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # Format x-axis dates
        ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('days_since_last_post.svg', format='svg', bbox_inches='tight')
        plt.close()


def create_combined_plot(stats, gap_data):
    """Create a 2x2 combined plot with all four charts."""
    # Extract data for plotting
    years = [stat['year'] for stat in stats]
    years_str = [str(year) for year in years]
    posts = [stat['posts'] for stat in stats]
    avg_words = [stat['avg_words_per_post'] for stat in stats]
    total_words = [stat['total_words'] for stat in stats]
    dates, gaps = gap_data
    
    # Create 2x2 subplot
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12), dpi=300)
    
    # 1. Posts per Year (top-left)
    bars1 = ax1.bar(years, posts, color='#2196F3', alpha=0.7)
    ax1.set_title('Posts per Year', pad=15, fontsize=12)
    ax1.set_xlabel('Year', fontsize=10)
    ax1.set_ylabel('Number of Posts', fontsize=10)
    ax1.set_xticks(years)
    ax1.set_xticklabels(years_str)
    ax1.grid(True, linestyle='--', alpha=0.7)
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}', ha='center', va='bottom', fontsize=8)
    
    # 2. Average Words per Post (top-right)
    ax2.plot(years, avg_words, marker='o', color='#4CAF50', linewidth=2)
    ax2.set_title('Average Words per Post', pad=15, fontsize=12)
    ax2.set_xlabel('Year', fontsize=10)
    ax2.set_ylabel('Words', fontsize=10)
    ax2.set_xticks(years)
    ax2.set_xticklabels(years_str)
    ax2.grid(True, linestyle='--', alpha=0.7)
    for x, y in zip(years, avg_words):
        ax2.text(x, y, f'{int(y)}', ha='center', va='bottom', fontsize=8)
    
    # 3. Total Words per Year (bottom-left)
    bars3 = ax3.bar(years, total_words, color='#FF9800', alpha=0.7)
    ax3.set_title('Total Words per Year', pad=15, fontsize=12)
    ax3.set_xlabel('Year', fontsize=10)
    ax3.set_ylabel('Words', fontsize=10)
    ax3.set_xticks(years)
    ax3.set_xticklabels(years_str)
    ax3.grid(True, linestyle='--', alpha=0.7)
    for bar in bars3:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}', ha='center', va='bottom', fontsize=8)
    
    # 4. Days Since Last Post (bottom-right)
    if dates and gaps:
        ax4.plot(dates, gaps, marker='o', color='#9C27B0', linewidth=2, markersize=4)
        ax4.set_title('Days Since Last Post', pad=15, fontsize=12)
        ax4.set_xlabel('Date', fontsize=10)
        ax4.set_ylabel('Days', fontsize=10)
        ax4.grid(True, linestyle='--', alpha=0.7)
        ax4.tick_params(axis='x', rotation=45, labelsize=8)
    
    plt.tight_layout()
    plt.savefig('blog_stats_combined.svg', format='svg', bbox_inches='tight')
    plt.close()


if __name__ == "__main__":
    blog_directory = "blog/raw/"

    data = analyze_posts_with_gaps(blog_directory)
    stats, gap_data = data
#    if os.path.isfile('out.json'):
#        with open('out.json', 'r') as fd:
#            data = json.load(fd)
#            print(len(data))
#            stats, gap_data = data
#    else:
#        data = analyze_posts_with_gaps(blog_directory)
#        with open('out.json', 'w') as fd:
#            json.dump(data, fd)
#        stats, gap_data = data
    
    # Print statistics
    print("\nBlog Statistics by Year:")
    print("-" * 65)
    print(f"{'Year':<10} {'Posts':<10} {'Total Words':<15} {'Avg Words/Post':<15}")
    print("-" * 65)
    total = 0
    for year_stat in stats:
        total += year_stat['total_words']
        print(f"{year_stat['year']:<10} {year_stat['posts']:<10} "
              f"{year_stat['total_words']:<15} {year_stat['avg_words_per_post']:<15.2f}")
    
    # Create and save visualizations
    create_and_save_plots(stats, gap_data)
    create_combined_plot(stats, gap_data)
    print(f"\nIndividual plots saved as SVG files")
    print(f"Combined plot saved as 'blog_stats_combined.svg'")
    print(f"total {total}")
