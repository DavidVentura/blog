from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

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

    return results, (dates, gaps), all_posts


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
    #plt.savefig('posts_per_year.svg', format='svg', bbox_inches='tight')
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
    #plt.savefig('avg_words_per_post.svg', format='svg', bbox_inches='tight')
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
    #plt.savefig('total_words_per_year.svg', format='svg', bbox_inches='tight')
    plt.close()
    
    # 4. Days Since Last Post
    dates, gaps = gap_data
    if dates and gaps:
        fig, ax = plt.subplots(**plot_kwargs)
        ax.plot(dates, gaps, marker='o', color='#9C27B0', linewidth=0, markersize=4)
        ax.set_title('Days Since Last Post', pad=15, fontsize=14)
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Days', fontsize=12)
        ax.set_yscale('linear')
        ax.set_ylim(bottom=0, top=400)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f'{int(y)}'))
        ax.grid(True, linestyle='--', alpha=0.7)

        # Format x-axis dates
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()
        #plt.savefig('days_since_last_post.svg', format='svg', bbox_inches='tight')
        plt.close()


def create_histogram_distribution_plot(stats, gap_data):
    """Alternative visualization: histogram with variable-width bins."""
    dates, gaps = gap_data

    if not dates or not gaps:
        return

    plot_kwargs = {
        'figsize': (10, 6),
        'dpi': 300
    }

    fig, ax = plt.subplots(**plot_kwargs)
    # Custom bins: dense at low end (0-100), sparse at high end
    bins = list(range(0, 110, 10)) + [150, 200, 300, 500]
    counts, bin_edges = np.histogram(gaps, bins=bins)

    # Create labels for each bin
    labels = [f'{int(bin_edges[i])}-{int(bin_edges[i+1])}' for i in range(len(bin_edges)-1)]

    # Plot as bar chart with equal widths
    x_pos = np.arange(len(labels))
    ax.bar(x_pos, counts, color='#9C27B0', alpha=0.7, edgecolor='black')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_title('Distribution of Days Between Posts', pad=15, fontsize=14)
    ax.set_xlabel('Days', fontsize=12)
    ax.set_ylabel('Number of Gaps', fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.7, axis='y')

    plt.tight_layout()
    plt.savefig('days_between_posts_histogram.svg', format='svg', bbox_inches='tight')
    plt.close()


def create_combined_plot(stats, gap_data, all_posts):
    """Create a 2x2 combined plot with all four charts and a stats table."""
    # Extract data for plotting
    years = [stat['year'] for stat in stats]
    years_str = [str(year) for year in years]
    posts = [stat['posts'] for stat in stats]
    avg_words = [stat['avg_words_per_post'] for stat in stats]
    total_words = [stat['total_words'] for stat in stats]
    dates, gaps = gap_data

    # Calculate overall statistics
    total_posts = sum(posts)
    total_words_count = sum(total_words)

    if all_posts and len(all_posts) > 1:
        first_post_date = all_posts[0]['date']
        last_post_date = all_posts[-1]['date']
        days_span = (last_post_date - first_post_date).days
        avg_days_between_posts = days_span / (len(all_posts) - 1) if len(all_posts) > 1 else 0
        years_span = days_span / 365.25
        avg_words_per_year = total_words_count / years_span if years_span > 0 else 0
        avg_posts_per_year = total_posts / years_span if years_span > 0 else 0
    else:
        days_span = 0
        avg_days_between_posts = 0
        avg_words_per_year = 0
        avg_posts_per_year = 0

    # Create figure with custom layout: 2x2 grid for plots, 1 narrow column for stats
    fig = plt.figure(figsize=(18, 12), dpi=300)
    gs = fig.add_gridspec(2, 3, width_ratios=[1, 1, 0.05], hspace=0.3, wspace=0.2)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, 0])
    ax4 = fig.add_subplot(gs[1, 1])
    ax_stats = fig.add_subplot(gs[:, 2])
    
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
        ax4.plot(dates, gaps, marker='o', color='#9C27B0', linewidth=0, markersize=4)
        ax4.set_title('Days Since Last Post', pad=15, fontsize=12)
        ax4.set_xlabel('Date', fontsize=10)
        ax4.set_ylabel('Days', fontsize=10)
        ax4.set_yscale('linear')
        ax4.set_ylim(bottom=0, top=300)
        ax4.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f'{int(y)}'))
        ax4.grid(True, linestyle='--', alpha=0.7)
        ax4.tick_params(axis='x', rotation=45, labelsize=8)

    # 5. Stats Table (right side - margin note style)
    ax_stats.axis('off')
    #ax_stats.set_title('Overall Statistics', pad=15, fontsize=10, fontweight='bold', loc='left')

    stats_text = f"""Total Posts: {total_posts}
Total Words: {total_words_count:,}
Days Span: {days_span}
Avg Days Between Posts: {avg_days_between_posts:.1f}
Avg Words per Year: {avg_words_per_year:,.0f}
Avg Posts per Year: {avg_posts_per_year:.1f}"""

    ax_stats.text(-2.05, 0.94, stats_text,
                  transform=ax_stats.transAxes,
                  fontsize=12,
                  verticalalignment='center',
                  horizontalalignment='left',
                  family='monospace')

    plt.savefig('blog_stats_combined.svg', format='svg', bbox_inches='tight')
    plt.close()


if __name__ == "__main__":
    blog_directory = "blog/raw/"

    stats, gap_data, all_posts = analyze_posts_with_gaps(blog_directory)
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
    create_combined_plot(stats, gap_data, all_posts)
    print(f"\nIndividual plots saved as SVG files")
    print(f"Combined plot saved as 'blog_stats_combined.svg'")
    print(f"total {total}")
