package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sort"

	abci "github.com/cometbft/cometbft/abci/types"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
)

type latestBlockResponse struct {
	Block struct {
		Header struct {
			ChainID string `json:"chain_id"`
			Height  string `json:"height"`
			Time    string `json:"time"`
		} `json:"header"`
		Data struct {
			Txs []string `json:"txs"`
		} `json:"data"`
	} `json:"block"`
}

func main() {
	const endpoint = "https://heimdall-api.polygon.technology/cosmos/base/tendermint/v1beta1/blocks/latest"

	resp, err := http.Get(endpoint)
	if err != nil {
		fail(err)
	}
	defer resp.Body.Close()

	var block latestBlockResponse
	if err := json.NewDecoder(resp.Body).Decode(&block); err != nil {
		fail(err)
	}
	if len(block.Block.Data.Txs) == 0 {
		fail(fmt.Errorf("latest block has no txs"))
	}

	tx0, err := base64.StdEncoding.DecodeString(block.Block.Data.Txs[0])
	if err != nil {
		fail(err)
	}

	var commit abci.ExtendedCommitInfo
	if err := commit.Unmarshal(tx0); err != nil {
		fail(fmt.Errorf("tx[0] is not ExtendedCommitInfo: %w", err))
	}

	placeholders := 0
	commitVotes := 0
	totalVP := int64(0)
	powers := make([]int64, 0, len(commit.Votes))
	for _, vote := range commit.Votes {
		if vote.BlockIdFlag == cmtproto.BlockIDFlagCommit {
			commitVotes++
			totalVP += vote.Validator.Power
			powers = append(powers, vote.Validator.Power)
		}
		if vote.BlockIdFlag == cmtproto.BlockIDFlagCommit &&
			len(vote.VoteExtension) == 0 &&
			len(vote.ExtensionSignature) == 0 &&
			len(vote.NonRpVoteExtension) == 0 &&
			len(vote.NonRpExtensionSignature) == 0 {
			placeholders++
		}
	}

	fmt.Printf("chain_id=%s\n", block.Block.Header.ChainID)
	fmt.Printf("height=%s\n", block.Block.Header.Height)
	fmt.Printf("time=%s\n", block.Block.Header.Time)
	fmt.Printf("block_txs=%d\n", len(block.Block.Data.Txs))
	fmt.Printf("tx0_decodes_as=abci.ExtendedCommitInfo\n")
	fmt.Printf("extended_commit_round=%d\n", commit.Round)
	fmt.Printf("extended_commit_votes=%d\n", len(commit.Votes))
	fmt.Printf("commit_flag_votes=%d\n", commitVotes)
	fmt.Printf("filtered_placeholder_votes=%d\n", placeholders)
	fmt.Printf("total_commit_voting_power=%d\n", totalVP)
	fmt.Printf("two_thirds_floor=%d\n", totalVP*2/3)
	fmt.Printf("min_signed_vp_to_pass=%d\n", totalVP*2/3+1)
	fmt.Printf("max_suppressible_vp_with_all_commit_votes=%d\n", totalVP-(totalVP*2/3+1))
	sort.Slice(powers, func(i, j int) bool { return powers[i] > powers[j] })
	fmt.Printf("commit_vote_powers_desc=%v\n", powers)
	if len(commit.Votes) > 0 {
		vote := commit.Votes[0]
		fmt.Printf("first_vote_extension_bytes=%d\n", len(vote.VoteExtension))
		fmt.Printf("first_extension_signature_bytes=%d\n", len(vote.ExtensionSignature))
		fmt.Printf("first_non_rp_vote_extension_bytes=%d\n", len(vote.NonRpVoteExtension))
		fmt.Printf("first_non_rp_extension_signature_bytes=%d\n", len(vote.NonRpExtensionSignature))
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
